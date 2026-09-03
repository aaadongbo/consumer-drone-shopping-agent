"""Multi-product, evidence-based recommendation walking skeleton for Slice 6."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from backend.agent import (
    EvidenceObjective,
    PerProductEvidenceBudget,
    RecommendationActionObservation,
    RecommendationActionPlan,
    RecommendationActionRoundTrace,
    RecommendationEvidenceAction,
    RecommendationExplanationResult,
    RecommendationFallback,
    RecommendationFallbackReason,
    build_recommendation_explanation,
)
from backend.catalog import (
    CatalogFixtureSnapshot,
    evaluate_store_eligibility,
    rank_eligible_variants_by_soft_preferences,
)
from backend.catalog.commerce_refresh import (
    CommerceRefreshResult,
    refresh_and_recheck_candidate,
)
from backend.common import (
    AttributeValue,
    ToolStatus,
    TurnRequest,
    VariantRecord,
)
from backend.common.contracts import WireModel
from backend.conversation import (
    NormalizedConstraint,
    normalize_constraint_patches,
    parse_constraint_patches,
)
from backend.evidence import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    CoverageStatus,
    DerivedEvidence,
    EvidenceCoverage,
    EvidenceSourceKind,
    derive_budget_margin,
)
from backend.rag import RetrievalRequest
from backend.rag.retrieval import RetrievalResult
from backend.shopify import ShopifyReadPort

_MAX_ACTION_ROUNDS = 2
_MAX_TOOL_CALLS = 2
_MAX_RETRIEVAL_TOKENS = 4000
_TURN_DEADLINE = timedelta(milliseconds=8000)


class CatalogProvider(Protocol):
    """Read-only Catalog capability used by the recommendation flow."""

    def load_store(self, *, store_id: str) -> CatalogFixtureSnapshot: ...


class RecommendationRetriever(Protocol):
    """Typed Product RAG capability; no generic tool dispatch is allowed."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...


class RecommendationTraceEventType(StrEnum):
    CANDIDATE_SELECTED = "CANDIDATE_SELECTED"
    CANDIDATE_REJECTED = "CANDIDATE_REJECTED"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    DERIVED_EVIDENCE_COMPUTED = "DERIVED_EVIDENCE_COMPUTED"
    EXPLANATION_BUILT = "EXPLANATION_BUILT"
    FALLBACK = "FALLBACK"


class RecommendationTraceEvent(WireModel):
    """Summary-only per-candidate trace event."""

    correlation_id: str = Field(min_length=1)
    event_type: RecommendationTraceEventType
    candidate: CandidateIdentity | None = None
    detail: str = Field(min_length=1)


class RecommendationCandidateResult(WireModel):
    """One candidate with isolated evidence and explanation outcome."""

    candidate: CandidateIdentity
    eligibility_eligible: bool
    evidence_bundle: CandidateEvidenceBundle
    explanation: RecommendationExplanationResult


class RecommendationFlowResult(WireModel):
    """Internal multi-product output; public multi-card schema remains deferred."""

    correlation_id: str = Field(min_length=1)
    candidates: tuple[RecommendationCandidateResult, ...] = Field(max_length=3)
    rejected_candidates: tuple[CandidateIdentity, ...] = ()
    fallback: RecommendationFallback | None = None
    trace: tuple[RecommendationTraceEvent, ...] = ()
    action_plan: RecommendationActionPlan | None = None
    action_round_traces: tuple[RecommendationActionRoundTrace, ...] = ()


class MultiProductRecommendationService:
    """Compose up to three candidate groups using only scoped evidence."""

    def __init__(
        self,
        *,
        catalog: CatalogProvider,
        shopify: ShopifyReadPort,
        retriever: RecommendationRetriever | None = None,
        correlation_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._shopify = shopify
        self._retriever = retriever
        self._correlation_id_factory = correlation_id_factory or _default_correlation_id
        self._clock = clock or (lambda: datetime.now(UTC))

    def recommend(self, request: TurnRequest) -> RecommendationFlowResult:
        correlation_id = self._correlation_id_factory()
        started_at = self._clock()
        snapshot = self._catalog.load_store(store_id=request.store_id)
        constraints = normalize_constraint_patches(parse_constraint_patches(request))
        eligibility = evaluate_store_eligibility(
            snapshot=snapshot, constraints=constraints
        )
        scores = rank_eligible_variants_by_soft_preferences(
            snapshot=snapshot,
            eligibility_results=eligibility,
            constraints=constraints,
        )
        variant_by_identity = {
            (variant.store_id, variant.product_id, variant.variant_id): variant
            for variant in snapshot.variants
        }
        product_ids: set[str] = set()
        selected: list[tuple[CandidateIdentity, VariantRecord]] = []
        for score in scores:
            candidate = CandidateIdentity(
                store_id=score.store_id,
                product_id=score.product_id,
                variant_id=score.variant_id,
            )
            if candidate.product_id in product_ids:
                continue
            variant = variant_by_identity.get(
                (candidate.store_id, candidate.product_id, candidate.variant_id)
            )
            if variant is None:
                continue
            selected.append((candidate, variant))
            product_ids.add(candidate.product_id)
            if len(selected) == 3:
                break

        traces: list[RecommendationTraceEvent] = []
        action_traces: list[RecommendationActionRoundTrace] = []
        results: list[RecommendationCandidateResult] = []
        rejected: list[CandidateIdentity] = []
        candidate_fallbacks: list[RecommendationFallback] = []
        action_plan = _build_action_plan(selected, question=request.user_text)
        tool_calls = 0
        retrieval_tokens = 0
        action_rounds = 0
        for candidate, variant in selected:
            if _deadline_exceeded(started_at, self._clock()):
                _append_budget_trace(
                    action_traces,
                    candidate=candidate,
                    round_number=min(action_rounds + 1, 2),
                    action=RecommendationEvidenceAction.REFRESH_COMMERCE,
                    tool_calls=tool_calls,
                    retrieval_tokens=retrieval_tokens,
                    stop_reason="TURN_DEADLINE",
                )
                break
            if tool_calls >= _MAX_TOOL_CALLS or action_rounds >= _MAX_ACTION_ROUNDS:
                _append_budget_trace(
                    action_traces,
                    candidate=candidate,
                    round_number=min(action_rounds + 1, 2),
                    action=RecommendationEvidenceAction.REFRESH_COMMERCE,
                    tool_calls=tool_calls,
                    retrieval_tokens=retrieval_tokens,
                    stop_reason="TOOL_CALL_LIMIT",
                )
                break
            traces.append(
                _trace(
                    correlation_id,
                    RecommendationTraceEventType.CANDIDATE_SELECTED,
                    candidate,
                    "Candidate passed initial deterministic eligibility ordering.",
                )
            )
            refreshed = refresh_and_recheck_candidate(
                shopify=self._shopify,
                variant=variant,
                constraints=constraints,
                now=self._clock(),
            )
            tool_calls += 1
            action_rounds += 1
            _append_action_trace(
                action_traces,
                candidate=candidate,
                round_number=action_rounds,
                action=RecommendationEvidenceAction.REFRESH_COMMERCE,
                evidence_count=len(refreshed.evidence),
                missing_fields=tuple(refreshed.result.missing_fields),
                tool_calls=tool_calls,
                retrieval_tokens=retrieval_tokens,
                choice_reason=(
                    "Refresh current commerce before eligibility and explanation."
                ),
            )
            if not refreshed.eligibility.eligible:
                rejected.append(candidate)
                traces.append(
                    _trace(
                        correlation_id,
                        RecommendationTraceEventType.CANDIDATE_REJECTED,
                        candidate,
                        _rejection_detail(refreshed),
                    )
                )
                continue
            rag_items: tuple[CandidateEvidence, ...] = ()
            if self._retriever is not None:
                if tool_calls >= _MAX_TOOL_CALLS or action_rounds >= _MAX_ACTION_ROUNDS:
                    _append_budget_trace(
                        action_traces,
                        candidate=candidate,
                        round_number=2,
                        action=RecommendationEvidenceAction.RETRIEVE_PRODUCT_EVIDENCE,
                        tool_calls=tool_calls,
                        retrieval_tokens=retrieval_tokens,
                        stop_reason="TOOL_CALL_LIMIT",
                    )
                else:
                    try:
                        rag_items = self._rag_evidence(request, candidate)
                        retrieval_tokens += sum(
                            len(item.text.split())
                            for item in rag_items
                            if item.text is not None
                        )
                        tool_calls += 1
                        action_rounds += 1
                        if retrieval_tokens > _MAX_RETRIEVAL_TOKENS:
                            rag_items = ()
                            _append_action_trace(
                                action_traces,
                                candidate=candidate,
                                round_number=action_rounds,
                                action=RecommendationEvidenceAction.RETRIEVE_PRODUCT_EVIDENCE,
                                evidence_count=0,
                                missing_fields=("rag",),
                                tool_calls=tool_calls,
                                retrieval_tokens=retrieval_tokens,
                                choice_reason=(
                                    "Reject retrieval output at the hard token budget."
                                ),
                                final_stop_reason="RETRIEVAL_TOKEN_BUDGET",
                            )
                        else:
                            _append_action_trace(
                                action_traces,
                                candidate=candidate,
                                round_number=action_rounds,
                                action=RecommendationEvidenceAction.RETRIEVE_PRODUCT_EVIDENCE,
                                evidence_count=len(rag_items),
                                missing_fields=(),
                                tool_calls=tool_calls,
                                retrieval_tokens=retrieval_tokens,
                                choice_reason=(
                                    "Collect only candidate-scoped Product "
                                    "RAG evidence."
                                ),
                            )
                    except ValueError:
                        tool_calls += 1
                        action_rounds += 1
                        _append_action_trace(
                            action_traces,
                            candidate=candidate,
                            round_number=action_rounds,
                            action=RecommendationEvidenceAction.RETRIEVE_PRODUCT_EVIDENCE,
                            evidence_count=0,
                            missing_fields=("rag",),
                            tool_calls=tool_calls,
                            retrieval_tokens=retrieval_tokens,
                            choice_reason=(
                                "Reject retrieval output that does not prove "
                                "candidate scope."
                            ),
                            final_stop_reason="RAG_SCOPE_MISMATCH",
                        )
            bundle = self._bundle_for(
                request=request,
                snapshot=snapshot,
                variant=variant,
                candidate=candidate,
                refreshed=refreshed,
                constraints=constraints,
                rag_items=rag_items,
            )
            traces.append(
                _trace(
                    correlation_id,
                    RecommendationTraceEventType.EVIDENCE_COLLECTED,
                    candidate,
                    "Candidate-scoped catalog, commerce and RAG evidence collected.",
                )
            )
            explanation = build_recommendation_explanation(
                bundle,
                requested_fields=("price", "use_case", "camera_resolution"),
                critical_fields=("price",),
                tradeoffs=bundle.derived_evidence,
            )
            if bundle.derived_evidence:
                traces.append(
                    _trace(
                        correlation_id,
                        RecommendationTraceEventType.DERIVED_EVIDENCE_COMPUTED,
                        candidate,
                        "Derived values replayed from candidate evidence inputs.",
                    )
                )
            traces.append(
                _trace(
                    correlation_id,
                    RecommendationTraceEventType.EXPLANATION_BUILT,
                    candidate,
                    "Explanation coverage evaluated without cross-candidate evidence.",
                )
            )
            if explanation.explanation is None:
                if explanation.fallback is not None:
                    candidate_fallbacks.append(explanation.fallback)
                    traces.append(
                        _trace(
                            correlation_id,
                            RecommendationTraceEventType.FALLBACK,
                            candidate,
                            (
                                "Candidate explanation degraded: "
                                f"{explanation.fallback.reason.value}."
                            ),
                        )
                    )
                continue
            results.append(
                RecommendationCandidateResult(
                    candidate=candidate,
                    eligibility_eligible=True,
                    evidence_bundle=bundle,
                    explanation=explanation,
                )
            )

        fallback = None
        if not results:
            fallback = (
                candidate_fallbacks[0]
                if candidate_fallbacks
                else RecommendationFallback(
                    reason=RecommendationFallbackReason.NO_MATCH,
                    message=(
                        "No candidate satisfies current availability and HARD "
                        "constraints."
                    ),
                )
            )
            traces.append(
                _trace(
                    correlation_id,
                    RecommendationTraceEventType.FALLBACK,
                    None,
                    "No eligible candidate remained after current commerce recheck.",
                )
            )
        return RecommendationFlowResult(
            correlation_id=correlation_id,
            candidates=tuple(results),
            rejected_candidates=tuple(rejected),
            fallback=fallback,
            trace=tuple(traces),
            action_plan=action_plan,
            action_round_traces=tuple(action_traces),
        )

    def _bundle_for(
        self,
        *,
        request: TurnRequest,
        snapshot: CatalogFixtureSnapshot,
        variant: VariantRecord,
        candidate: CandidateIdentity,
        refreshed: CommerceRefreshResult,
        constraints: tuple[NormalizedConstraint, ...],
        rag_items: tuple[CandidateEvidence, ...],
    ) -> CandidateEvidenceBundle:
        product = next(
            item
            for item in snapshot.products
            if (item.store_id, item.product_id)
            == (candidate.store_id, candidate.product_id)
        )
        catalog_items = tuple(
            _catalog_evidence(candidate, field, fact)
            for field, fact in (
                *product.shared_attributes.items(),
                *variant.variant_attributes.items(),
            )
        )
        derived = self._derived_evidence(candidate, refreshed, constraints)
        required_fields = ("price", "use_case", "camera_resolution")
        covered = tuple(
            field
            for field in required_fields
            if any(
                item.field == field
                for item in (*catalog_items, *refreshed.evidence, *rag_items)
            )
        )
        missing = tuple(field for field in required_fields if field not in covered)
        coverage_status = (
            CoverageStatus.COMPLETE
            if not missing
            else CoverageStatus.PARTIAL
            if covered
            else CoverageStatus.MISSING
        )
        return CandidateEvidenceBundle(
            candidate=candidate,
            catalog_evidence=catalog_items,
            commerce_evidence=refreshed.evidence,
            rag_evidence=rag_items,
            derived_evidence=derived,
            coverage=EvidenceCoverage(
                status=coverage_status,
                required_fields=required_fields,
                covered_fields=covered,
                missing_fields=missing,
            ),
        )

    def _rag_evidence(
        self, request: TurnRequest, candidate: CandidateIdentity
    ) -> tuple[CandidateEvidence, ...]:
        if self._retriever is None:
            return ()
        result = self._retriever.retrieve(
            RetrievalRequest(
                turn_target=candidate.as_scope(),
                question=request.user_text,
            )
        )
        if result.request.turn_target != candidate.as_scope():
            raise ValueError("retrieval result crossed candidate identity")
        if any(
            chunk.store_id != candidate.store_id
            or chunk.product_id != candidate.product_id
            or chunk.variant_id not in (None, candidate.variant_id)
            for chunk in result.evidence
        ):
            raise ValueError("retrieval evidence crossed candidate identity")
        return tuple(
            CandidateEvidence(
                evidence_id=f"rag-{candidate.product_id}-{candidate.variant_id}-{chunk.chunk_id}",
                source_kind=EvidenceSourceKind.RAG,
                candidate=candidate,
                field=chunk.source_type.value.casefold(),
                text=chunk.text,
                source_ref=chunk.locator.locator,
            )
            for chunk in result.evidence
        )

    @staticmethod
    def _derived_evidence(
        candidate: CandidateIdentity,
        refreshed: CommerceRefreshResult,
        constraints: tuple[NormalizedConstraint, ...],
    ) -> tuple[DerivedEvidence, ...]:
        budget = next(
            (
                item.value
                for item in constraints
                if item.field.value == "price"
                and isinstance(item.value, int | float)
                and not isinstance(item.value, bool)
            ),
            None,
        )
        price = next(
            (item for item in refreshed.evidence if item.field == "price"), None
        )
        if budget is None or price is None:
            return ()
        return (
            derive_budget_margin(
                candidate=candidate, price_evidence=price, budget=budget
            ),
        )


def _catalog_evidence(
    candidate: CandidateIdentity, field: str, fact: AttributeValue
) -> CandidateEvidence:
    return CandidateEvidence(
        evidence_id=f"catalog-{candidate.product_id}-{candidate.variant_id}-{field}",
        source_kind=EvidenceSourceKind.CATALOG,
        candidate=candidate,
        field=field,
        fact=fact,
        source_ref=fact.source_ref,
        observed_at=fact.observed_at,
    )


def _rejection_detail(result: CommerceRefreshResult) -> str:
    if result.result.status is ToolStatus.ERROR:
        return f"Current commerce refresh failed: {result.result.error_code}."
    return "Current commerce or HARD eligibility check rejected the candidate."


def _build_action_plan(
    selected: list[tuple[CandidateIdentity, VariantRecord]], *, question: str
) -> RecommendationActionPlan | None:
    if not selected:
        return None
    candidates = tuple(candidate for candidate, _ in selected)
    return RecommendationActionPlan(
        candidate_set=candidates,
        evidence_objectives=tuple(
            EvidenceObjective(
                candidate=candidate,
                field="recommendation_evidence",
                question=question,
            )
            for candidate in candidates
        ),
        per_product_budgets=tuple(
            PerProductEvidenceBudget(candidate=candidate) for candidate in candidates
        ),
        max_action_rounds=_MAX_ACTION_ROUNDS,
    )


def _append_action_trace(
    traces: list[RecommendationActionRoundTrace],
    *,
    candidate: CandidateIdentity,
    round_number: int,
    action: RecommendationEvidenceAction,
    evidence_count: int,
    missing_fields: tuple[str, ...],
    tool_calls: int,
    retrieval_tokens: int,
    choice_reason: str,
    final_stop_reason: str | None = None,
) -> None:
    observation = RecommendationActionObservation(
        action=action,
        candidate=candidate,
        evidence_count=evidence_count,
        missing_fields=missing_fields,
    )
    traces.append(
        RecommendationActionRoundTrace(
            round_number=round_number,
            action=action,
            candidate=candidate,
            choice_reason=choice_reason,
            observation=observation,
            budget_tool_calls=tool_calls,
            budget_retrieval_tokens=retrieval_tokens,
            final_stop_reason=final_stop_reason,
        )
    )


def _append_budget_trace(
    traces: list[RecommendationActionRoundTrace],
    *,
    candidate: CandidateIdentity,
    round_number: int,
    action: RecommendationEvidenceAction,
    tool_calls: int,
    retrieval_tokens: int,
    stop_reason: str,
) -> None:
    _append_action_trace(
        traces,
        candidate=candidate,
        round_number=round_number,
        action=action,
        evidence_count=0,
        missing_fields=("budget",),
        tool_calls=tool_calls,
        retrieval_tokens=retrieval_tokens,
        choice_reason="Stop before an action that would exceed the turn budget.",
        final_stop_reason=stop_reason,
    )


def _deadline_exceeded(started_at: datetime, now: datetime) -> bool:
    return now - started_at >= _TURN_DEADLINE


def _trace(
    correlation_id: str,
    event_type: RecommendationTraceEventType,
    candidate: CandidateIdentity | None,
    detail: str,
) -> RecommendationTraceEvent:
    return RecommendationTraceEvent(
        correlation_id=correlation_id,
        event_type=event_type,
        candidate=candidate,
        detail=detail,
    )


def _default_correlation_id() -> str:
    return "slice6-recommendation"


__all__ = [
    "CatalogProvider",
    "MultiProductRecommendationService",
    "RecommendationCandidateResult",
    "RecommendationFlowResult",
    "RecommendationRetriever",
    "RecommendationTraceEvent",
    "RecommendationTraceEventType",
]
