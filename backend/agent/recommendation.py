"""Deterministic Slice 2 single-turn recommendation walking skeleton."""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from backend.catalog import (
    CatalogFixtureSnapshot,
    evaluate_store_eligibility,
    rank_eligible_variants_by_soft_preferences,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    AnswerPayload,
    EnvelopeOutcome,
    FallbackPayload,
    FallbackReasonCode,
    FreshnessDisclosure,
    ObjectScope,
    StandardFallback,
    ToolStatus,
    TraceEvent,
    TraceEventType,
    TraceOperation,
    TraceResult,
    TraceSummary,
    TurnRequest,
)
from backend.conversation import normalize_constraint_patches, parse_constraint_patches
from backend.evidence import (
    RecommendationCandidate,
    RecommendationCandidateSet,
    build_recommendation_candidates,
)

_SENSITIVE_TRACE_VALUE = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|password|secret|token|sk[-_])"
)


class CatalogSnapshotProvider(Protocol):
    """Minimal Slice 2 read capability used by the recommendation service."""

    def load_store(self, *, store_id: str) -> CatalogFixtureSnapshot: ...


class Slice2TraceSink:
    """Keep validated, summary-only Trace Contract events in memory."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def append(self, event: TraceEvent) -> None:
        self._events.append(event)


class Slice2RecommendationService:
    """Compose one deterministic recommendation answer or fail-closed fallback."""

    def __init__(
        self,
        *,
        catalog: CatalogSnapshotProvider,
        trace_sink: Slice2TraceSink,
        correlation_id_factory: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        self._catalog = catalog
        self._trace_sink = trace_sink
        self._correlation_id_factory = correlation_id_factory
        self._clock = clock

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        correlation_id = _safe_trace_value(self._correlation_id_factory())
        request_scope = _request_scope(request)
        self._trace(
            correlation_id,
            TraceEventType.TURN_REQUEST_ACCEPTED,
            TraceResult.ACCEPTED,
            scope=request_scope,
        )

        patches = parse_constraint_patches(request)
        constraints = normalize_constraint_patches(patches)
        self._trace(
            correlation_id,
            TraceEventType.ROUTE_DECISION,
            TraceResult.SUCCESS,
            scope=request_scope,
        )
        if not constraints:
            return self._fallback(
                request,
                correlation_id,
                request_scope,
                FallbackReasonCode.OUT_OF_SCOPE,
            )

        snapshot = self._catalog.load_store(store_id=request.store_id)
        self._trace(
            correlation_id,
            TraceEventType.SHOPIFY_READ_CALLED,
            TraceResult.ACCEPTED,
            scope=request_scope,
            operation=TraceOperation.REFRESH_COMMERCE_STATE,
        )
        if not _snapshot_matches_store(snapshot, request.store_id):
            return self._fallback(
                request,
                correlation_id,
                request_scope,
                FallbackReasonCode.PRODUCT_NOT_FOUND,
            )
        if not _snapshot_has_complete_commerce(snapshot):
            return self._fallback(
                request,
                correlation_id,
                request_scope,
                FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
            )
        self._trace_commerce_results(correlation_id, snapshot)
        if not snapshot.products or not snapshot.variants or not snapshot.commerce:
            return self._fallback(
                request,
                correlation_id,
                request_scope,
                FallbackReasonCode.PRODUCT_NOT_FOUND,
            )

        eligibility = evaluate_store_eligibility(
            snapshot=snapshot,
            constraints=constraints,
        )
        soft_scores = rank_eligible_variants_by_soft_preferences(
            snapshot=snapshot,
            eligibility_results=eligibility,
            constraints=constraints,
        )
        candidates = build_recommendation_candidates(
            snapshot=snapshot,
            eligibility_results=eligibility,
            soft_scores=soft_scores,
        )
        if not candidates.candidates:
            return self._fallback(
                request,
                correlation_id,
                request_scope,
                FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
            )
        return self._answer_from_candidate(
            request=request,
            correlation_id=correlation_id,
            candidate_set=candidates,
        )

    def _answer_from_candidate(
        self,
        *,
        request: TurnRequest,
        correlation_id: str,
        candidate_set: RecommendationCandidateSet,
    ) -> AnswerEnvelope:
        candidate = candidate_set.candidates[0]
        scope = ObjectScope(
            store_id=candidate.store_id,
            product_id=candidate.product_id,
            variant_id=candidate.variant_id,
        )
        claims = [reason.claim for reason in candidate.reasons]
        bindings = [reason.binding for reason in candidate.reasons]
        text = _recommendation_text(candidate, candidate_set)
        payload = AnswerPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.ANSWER,
            conversation=request.conversation,
            trace_correlation_id=correlation_id,
            resolved_scope=scope,
            text=text,
            claims=claims,
            product_card=candidate.product_card,
            evidence=list(candidate.evidence),
            bindings=bindings,
            freshness=_freshness(candidate),
        )
        envelope = AnswerEnvelope(root=payload)
        self._trace(
            correlation_id,
            TraceEventType.EVIDENCE_ACCEPTED,
            TraceResult.ACCEPTED,
            scope=scope,
        )
        self._trace(
            correlation_id,
            TraceEventType.ANSWER_PRODUCED,
            TraceResult.ANSWER,
            scope=scope,
        )
        return envelope

    def _fallback(
        self,
        request: TurnRequest,
        correlation_id: str,
        scope: ObjectScope,
        reason_code: FallbackReasonCode,
    ) -> AnswerEnvelope:
        message, retryable, next_actions = _fallback_copy(reason_code)
        payload = FallbackPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.FALLBACK,
            conversation=request.conversation,
            trace_correlation_id=correlation_id,
            resolved_scope=scope,
            text=message,
            fallback=StandardFallback(
                reason_code=reason_code,
                message=message,
                retryable=retryable,
                next_actions=list(next_actions),
                resolved_scope=scope,
            ),
        )
        envelope = AnswerEnvelope(root=payload)
        self._trace(
            correlation_id,
            TraceEventType.FALLBACK_PRODUCED,
            TraceResult.FALLBACK,
            scope=scope,
            fallback_reason=reason_code,
        )
        return envelope

    def _trace_commerce_results(
        self,
        correlation_id: str,
        snapshot: CatalogFixtureSnapshot,
    ) -> None:
        for entry in snapshot.commerce:
            scope = ObjectScope(
                store_id=entry.store_id,
                product_id=entry.product_id,
                variant_id=entry.variant_id,
            )
            self._trace(
                correlation_id,
                TraceEventType.TOOL_RESULT,
                _trace_result(entry.result.status),
                scope=scope,
                operation=TraceOperation.REFRESH_COMMERCE_STATE,
                tool_status=entry.result.status,
            )

    def _trace(
        self,
        correlation_id: str,
        event_type: TraceEventType,
        result: TraceResult,
        *,
        scope: ObjectScope,
        operation: TraceOperation | None = None,
        tool_status: ToolStatus | None = None,
        fallback_reason: FallbackReasonCode | None = None,
    ) -> None:
        self._trace_sink.append(
            TraceEvent(
                schema_version=SCHEMA_VERSION,
                correlation_id=_safe_trace_value(correlation_id),
                event_type=event_type,
                occurred_at=self._clock(),
                summary=TraceSummary(
                    result=result,
                    scope=_safe_trace_scope(scope),
                    operation=operation,
                    tool_status=tool_status,
                    fallback_reason=fallback_reason,
                ),
            )
        )


def _request_scope(request: TurnRequest) -> ObjectScope:
    return ObjectScope(
        store_id=request.store_id,
        product_id=request.page_context.product_id,
        variant_id=request.page_context.variant_id,
    )


def _snapshot_matches_store(
    snapshot: CatalogFixtureSnapshot,
    requested_store_id: str,
) -> bool:
    if snapshot.store_id != requested_store_id:
        return False
    if any(product.store_id != requested_store_id for product in snapshot.products):
        return False
    if any(variant.store_id != requested_store_id for variant in snapshot.variants):
        return False
    return not any(entry.store_id != requested_store_id for entry in snapshot.commerce)


def _snapshot_has_complete_commerce(snapshot: CatalogFixtureSnapshot) -> bool:
    variant_identities = {
        (variant.store_id, variant.product_id, variant.variant_id)
        for variant in snapshot.variants
    }
    commerce_identities = {
        (entry.store_id, entry.product_id, entry.variant_id)
        for entry in snapshot.commerce
    }
    return variant_identities == commerce_identities


def _recommendation_text(
    candidate: RecommendationCandidate,
    candidate_set: RecommendationCandidateSet,
) -> str:
    return (
        f"推荐 {candidate.product_card.display_title}（{candidate.variant_label}）。"
        f"本轮共有 {len(candidate_set.candidates)} 个不同商品候选；"
        f"首选 Variant 为 {candidate.variant_id}，"
        f"已通过硬约束并绑定 {len(candidate.evidence)} 条证据。"
    )


def _freshness(candidate: RecommendationCandidate) -> FreshnessDisclosure | None:
    for evidence in candidate.evidence:
        if evidence.observed_at is not None:
            return FreshnessDisclosure(
                observed_at=evidence.observed_at,
                source=evidence.source,
            )
    return None


def _fallback_copy(
    reason_code: FallbackReasonCode,
) -> tuple[str, bool, tuple[str, ...]]:
    return {
        FallbackReasonCode.OUT_OF_SCOPE: (
            "当前输入没有命中 Slice 2 支持的推荐约束。",
            False,
            ("补充预算、重量、电池数量或用途偏好",),
        ),
        FallbackReasonCode.PRODUCT_NOT_FOUND: (
            "当前商店没有可用于推荐的商品数据。",
            False,
            ("确认商店或目录数据",),
        ),
        FallbackReasonCode.FACT_UNKNOWN_OR_MISSING: (
            "没有可售 Variant 同时满足本轮硬约束。",
            False,
            ("放宽预算、重量或电池数量约束", "补充其他偏好"),
        ),
        FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR: (
            "暂时无法可靠生成推荐，请停止展示该结论并联系支持。",
            False,
            ("停止展示该结论", "联系支持"),
        ),
    }[reason_code]


def _trace_result(status: ToolStatus) -> TraceResult:
    return {
        ToolStatus.SUCCESS: TraceResult.SUCCESS,
        ToolStatus.PARTIAL: TraceResult.PARTIAL,
        ToolStatus.ERROR: TraceResult.ERROR,
    }[status]


def _safe_trace_scope(scope: ObjectScope) -> ObjectScope:
    return ObjectScope(
        store_id=_safe_trace_value(scope.store_id),
        product_id=_safe_trace_value(scope.product_id),
        variant_id=_safe_trace_value(scope.variant_id)
        if scope.variant_id is not None
        else None,
    )


def _safe_trace_value(value: str) -> str:
    if _SENSITIVE_TRACE_VALUE.search(value):
        return "[REDACTED]"
    return value
