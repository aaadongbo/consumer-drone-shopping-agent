"""Multi-product, evidence-based recommendation walking skeleton for Slice 6."""

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from backend.agent import (
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
        self._clock = clock or datetime.now

    def recommend(self, request: TurnRequest) -> RecommendationFlowResult:
        correlation_id = self._correlation_id_factory()
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
        results: list[RecommendationCandidateResult] = []
        rejected: list[CandidateIdentity] = []
        for candidate, variant in selected:
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
            bundle = self._bundle_for(
                request=request,
                snapshot=snapshot,
                variant=variant,
                candidate=candidate,
                refreshed=refreshed,
                constraints=constraints,
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
            fallback = RecommendationFallback(
                reason=RecommendationFallbackReason.NO_MATCH,
                message=(
                    "No candidate satisfies current availability and HARD constraints."
                ),
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
        rag_items = self._rag_evidence(request, candidate)
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
