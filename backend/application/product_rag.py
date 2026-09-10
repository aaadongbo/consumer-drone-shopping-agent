"""Slice 5 walking skeleton for single-target static Product RAG answers."""

import re
from collections.abc import Callable
from datetime import datetime

from backend.agent import BoundedProductRagLoop, ProductRagRetriever, RagStopReason
from backend.application.slice_1 import InMemoryTraceSink
from backend.application.target_fact_adapter import (
    TargetFactIdentityAdapter,
    TargetFactIdentityError,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    AnswerPayload,
    AttributeStatus,
    AttributeValue,
    Claim,
    ClaimEvidenceBinding,
    EnvelopeOutcome,
    Evidence,
    EvidenceType,
    FallbackPayload,
    FallbackReasonCode,
    ObjectScope,
    StandardFallback,
    TraceEvent,
    TraceEventType,
    TraceResult,
    TraceSummary,
    TurnRequest,
)
from backend.conversation import TargetResolution
from backend.evidence import RagClaim, gate_retrieval_evidence
from backend.rag import RetrievalRequest

_SENSITIVE_TRACE_VALUE = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|password|secret|token|sk[-_])"
)

_STATIC_QUESTION_TEMPLATES = (
    (
        (
            "battery",
            "batteries",
            "package",
            "what's in the box",
            "电池",
            "包装",
            "套装",
        ),
        "package_list",
        "Travel Pack includes three batteries.",
        "rag://drone-travel-package-list@docs-2026-09-01/chunk/000",
    ),
    (
        ("beginner", "flight mode", "flight modes", "新手", "飞行模式"),
        "faq",
        "The aircraft supports beginner flight modes and travel use.",
        "rag://drone-travel-faq@docs-2026-09-01/chunk/000",
    ),
    (
        ("takeoff", "propeller", "camera", "specification", "spec", "起飞", "螺旋桨"),
        "manual",
        (
            "Before takeoff, unfold the arms, power on the controller, "
            "and check propellers."
        ),
        "rag://drone-travel-manual@docs-2026-09-01/chunk/000",
    ),
    (
        ("care", "coverage", "policy", "warranty", "保障", "政策"),
        "policy",
        "Care coverage is available only for supported store regions.",
        "rag://drone-travel-policy@docs-2026-09-01/chunk/000",
    ),
    (
        ("compare", "comparison", "difference", "which is better", "比较", "区别"),
        "comparison",
        "A comparison requires product-scoped evidence for each named product.",
        "rag://drone-comparison@docs-2026-09-01/chunk/000",
    ),
    (
        ("recommend", "recommendation", "best for", "budget", "推荐", "预算"),
        "recommendation",
        (
            "A recommendation must stay within the products and evidence approved "
            "for this store."
        ),
        "rag://drone-recommendation@docs-2026-09-01/chunk/000",
    ),
)
_DYNAMIC_QUESTION_TERMS = (
    "price",
    "how much",
    "cost",
    "inventory",
    "in stock",
    "availability",
    "价格",
    "库存",
    "有货",
)


class ProductRagQuestionInterpreter:
    """Recognize only the approved static-document samples for this skeleton."""

    def interpret(
        self, *, text: str, scope: ObjectScope, locale: str = "zh-CN"
    ) -> RagClaim | None:
        normalized = text.casefold()
        if any(term in normalized for term in _DYNAMIC_QUESTION_TERMS):
            return RagClaim(
                claim_id="rag-dynamic-fact",
                scope=scope,
                field="price",
                text="dynamic commerce fact",
                locator="rag://dynamic-commerce@not-applicable/none",
            )
        for terms, field, claim_text, locator in _STATIC_QUESTION_TEMPLATES:
            if any(term in normalized for term in terms):
                return RagClaim(
                    claim_id=f"rag-{field}",
                    scope=scope,
                    field=field,
                    text=claim_text,
                    locator=locator,
                )
        return None


class ProductRagApplicationService:
    """Compose a public answer only from an accepted single-target RAG claim."""

    def __init__(
        self,
        *,
        loop: BoundedProductRagLoop,
        interpreter: ProductRagQuestionInterpreter,
        trace_sink: InMemoryTraceSink,
        correlation_id_factory: Callable[[], str],
        clock: Callable[[], datetime],
        retriever: ProductRagRetriever | None = None,
    ) -> None:
        self._loop = loop
        self._interpreter = interpreter
        self._trace_sink = trace_sink
        self._correlation_id_factory = correlation_id_factory
        self._clock = clock
        self._retriever = retriever

    def answer_resolved(
        self, request: TurnRequest, resolution: TargetResolution
    ) -> AnswerEnvelope:
        """Use an already resolved Slice 3 single-object target, never Page Context."""
        correlation_id = _safe_trace_value(self._correlation_id_factory())
        try:
            scope = TargetFactIdentityAdapter().resolve_scope(
                request=request, resolution=resolution
            )
        except TargetFactIdentityError:
            request_scope = ObjectScope(
                store_id=request.store_id,
                product_id=request.page_context.product_id,
                variant_id=request.page_context.variant_id,
            )
            self._trace(
                correlation_id,
                TraceEventType.TURN_REQUEST_ACCEPTED,
                TraceResult.ACCEPTED,
                request_scope,
            )
            return self._fallback(
                request=request,
                correlation_id=correlation_id,
                scope=request_scope,
                reason=RagStopReason.EVIDENCE_REJECTED,
            )

        self._trace(
            correlation_id,
            TraceEventType.TURN_REQUEST_ACCEPTED,
            TraceResult.ACCEPTED,
            scope,
        )
        self._trace(
            correlation_id,
            TraceEventType.ROUTE_DECISION,
            TraceResult.SUCCESS,
            scope,
        )
        claim = self._interpreter.interpret(
            text=request.user_text, scope=scope, locale=request.locale
        )
        if claim is None:
            return self._fallback(
                request=request,
                correlation_id=correlation_id,
                scope=scope,
                reason=RagStopReason.EVIDENCE_REJECTED,
            )

        retrieval_request = RetrievalRequest(
            turn_target=scope, question=request.user_text
        )
        if self._retriever is not None:
            # The live pilot resolves the user-visible claim from the exact
            # chunk returned by the bounded, scope-first retriever.  This
            # prevents fixture claim text/locators from crossing the runtime
            # boundary while leaving historical fixture tests unchanged.
            retrieval = self._retriever.retrieve(retrieval_request)
            runtime_claim = None
            selected = None
            for attempt in range(2):
                if retrieval.evidence:
                    candidate = retrieval.evidence[0]
                    candidate_claim = claim.model_copy(
                        update={
                            "text": candidate.text,
                            "locator": candidate.locator.locator,
                        }
                    )
                    gate = gate_retrieval_evidence(retrieval, claims=(candidate_claim,))
                    if gate.accepted_claim_ids:
                        selected = candidate
                        runtime_claim = candidate_claim
                        break
                if attempt == 0:
                    retrieval = self._retriever.retrieve(
                        retrieval_request.model_copy(update={"field_hint": claim.field})
                    )
            if selected is None or runtime_claim is None:
                self._trace(
                    correlation_id,
                    TraceEventType.EVIDENCE_REJECTED,
                    TraceResult.REJECTED,
                    scope,
                )
                return self._fallback(
                    request=request,
                    correlation_id=correlation_id,
                    scope=scope,
                    reason=RagStopReason.EVIDENCE_REJECTED,
                )
            if not _chunk_is_admitted_for_locale(
                selected,
                field=runtime_claim.field,
                scope=scope,
                locale=request.locale,
            ):
                return self._fallback(
                    request=request,
                    correlation_id=correlation_id,
                    scope=scope,
                    reason=RagStopReason.EVIDENCE_REJECTED,
                )
            return self._answer_from_chunk(
                request=request,
                correlation_id=correlation_id,
                scope=scope,
                claim=runtime_claim,
                chunk=selected,
                locator=selected.locator.locator,
            )

        loop_result = self._loop.run(
            request=retrieval_request,
            claim=claim,
        )
        if loop_result.stop_reason is not RagStopReason.EVIDENCE_ACCEPTED:
            self._trace(
                correlation_id,
                TraceEventType.EVIDENCE_REJECTED,
                TraceResult.REJECTED,
                scope,
            )
            return self._fallback(
                request=request,
                correlation_id=correlation_id,
                scope=scope,
                reason=loop_result.stop_reason,
            )

        assert loop_result.evidence_gate is not None
        quality = loop_result.evidence_gate.quality[0]
        locator = quality.evidence_locators[0]
        chunk = next(
            item
            for item in loop_result.evidence_gate.retrieval.evidence
            if item.locator.locator == locator
        )
        if not _chunk_is_admitted_for_locale(
            chunk,
            field=claim.field,
            scope=scope,
            locale=request.locale,
        ):
            return self._fallback(
                request=request,
                correlation_id=correlation_id,
                scope=scope,
                reason=RagStopReason.EVIDENCE_REJECTED,
            )
        return self._answer_from_chunk(
            request=request,
            correlation_id=correlation_id,
            scope=scope,
            claim=claim,
            chunk=chunk,
            locator=locator,
        )

    def _answer_from_chunk(
        self,
        *,
        request: TurnRequest,
        correlation_id: str,
        scope: ObjectScope,
        claim: RagClaim,
        chunk,
        locator: str,
    ) -> AnswerEnvelope:
        fact_text = claim.text
        fact = AttributeValue(
            status=AttributeStatus.KNOWN,
            value=fact_text,
            source_ref=locator,
        )
        evidence = Evidence(
            evidence_id=f"{correlation_id}-rag-e1",
            # The current public schema only has TOOL.  This is a typed local
            # retrieval tool result; a RAG-specific public evidence type would
            # be a future public Contract proposal, not a T06 change.
            type=EvidenceType.TOOL,
            store_id=chunk.store_id,
            product_id=chunk.product_id,
            variant_id=chunk.variant_id,
            field_locator=locator,
            fact=fact,
            source=chunk.locator.locator,
        )
        claim_wire = Claim(
            claim_id=f"{correlation_id}-rag-c1", field=claim.field, fact=fact
        )
        binding = ClaimEvidenceBinding(
            claim_id=claim_wire.claim_id, evidence_ids=[evidence.evidence_id]
        )
        payload = AnswerPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.ANSWER,
            conversation=request.conversation,
            trace_correlation_id=correlation_id,
            resolved_scope=scope,
            text=fact_text,
            claims=[claim_wire],
            evidence=[evidence],
            bindings=[binding],
        )
        self._trace(
            correlation_id,
            TraceEventType.EVIDENCE_ACCEPTED,
            TraceResult.ACCEPTED,
            scope,
        )
        self._trace(
            correlation_id,
            TraceEventType.ANSWER_PRODUCED,
            TraceResult.ANSWER,
            scope,
        )
        return AnswerEnvelope(root=payload)

    def fallback_resolved(
        self,
        request: TurnRequest,
        resolution: TargetResolution,
        *,
        reason: RagStopReason = RagStopReason.EVIDENCE_REJECTED,
    ) -> AnswerEnvelope:
        """Return a safe fallback for a resolved target without attempting RAG."""
        correlation_id = _safe_trace_value(self._correlation_id_factory())
        try:
            scope = TargetFactIdentityAdapter().resolve_scope(
                request=request, resolution=resolution
            )
        except TargetFactIdentityError:
            scope = ObjectScope(
                store_id=request.store_id,
                product_id=request.page_context.product_id,
                variant_id=request.page_context.variant_id,
            )
        self._trace(
            correlation_id,
            TraceEventType.TURN_REQUEST_ACCEPTED,
            TraceResult.ACCEPTED,
            scope,
        )
        return self._fallback(
            request=request,
            correlation_id=correlation_id,
            scope=scope,
            reason=reason,
        )

    def _fallback(
        self,
        *,
        request: TurnRequest,
        correlation_id: str,
        scope: ObjectScope,
        reason: RagStopReason,
    ) -> AnswerEnvelope:
        message, actions = _fallback_copy(reason, locale=request.locale)
        payload = FallbackPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.FALLBACK,
            conversation=request.conversation,
            trace_correlation_id=correlation_id,
            resolved_scope=scope,
            text=message,
            fallback=StandardFallback(
                reason_code=FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
                message=message,
                retryable=False,
                next_actions=list(actions),
                resolved_scope=scope,
            ),
        )
        self._trace(
            correlation_id,
            TraceEventType.FALLBACK_PRODUCED,
            TraceResult.FALLBACK,
            scope,
            fallback_reason=FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
        )
        return AnswerEnvelope(root=payload)

    def _trace(
        self,
        correlation_id: str,
        event_type: TraceEventType,
        result: TraceResult,
        scope: ObjectScope,
        *,
        fallback_reason: FallbackReasonCode | None = None,
    ) -> None:
        self._trace_sink.append(
            TraceEvent(
                schema_version=SCHEMA_VERSION,
                correlation_id=correlation_id,
                event_type=event_type,
                occurred_at=self._clock(),
                summary=TraceSummary(
                    result=result,
                    scope=_safe_scope(scope),
                    fallback_reason=fallback_reason,
                ),
            )
        )


def _fallback_copy(
    reason: RagStopReason, *, locale: str = "zh-CN"
) -> tuple[str, tuple[str, ...]]:
    if locale.casefold() == "en-us" and reason not in {
        RagStopReason.DYNAMIC_FACT_REQUIRED,
        RagStopReason.CLARIFICATION_REQUIRED,
    }:
        return (
            "I can help compare drones, explain product specifications, and check "
            "current availability. For orders, shipping, refunds, or after-sales "
            "support, please use the store's order help or contact support.",
            ("Choose a verified product or ask about a supported specification",),
        )
    if reason is RagStopReason.DYNAMIC_FACT_REQUIRED:
        return (
            "价格、库存和可售状态需要读取当前商品的实时商店数据。",
            ("查询当前商品的实时价格、库存或可售状态",),
        )
    if reason is RagStopReason.CLARIFICATION_REQUIRED:
        return (
            "当前授权资料不足以确认该问题，请补充具体资料范围。",
            ("补充具体规格、套装或使用场景",),
        )
    if reason in {
        RagStopReason.TURN_DEADLINE,
        RagStopReason.RETRIEVAL_TOKEN_BUDGET,
        RagStopReason.TOOL_CALL_LIMIT,
        RagStopReason.ACTION_ROUND_LIMIT,
    }:
        return (
            "本轮资料核验预算已耗尽，无法可靠确认该结论。",
            ("缩小问题范围后重试",),
        )
    return (
        "当前授权资料无法可靠确认该项事实。",
        ("查看其他已知规格", "联系商家确认"),
    )


def _english_claim(field: str) -> str:
    return {
        "package_list": (
            "The approved product evidence describes the package and included "
            "batteries."
        ),
        "faq": (
            "The approved product evidence describes supported flight modes and "
            "travel use."
        ),
        "manual": (
            "The approved product evidence describes the relevant setup and "
            "operating guidance."
        ),
        "policy": (
            "US-specific care, warranty, and policy claims require an explicitly "
            "applicable source."
        ),
        "comparison": (
            "I can compare products only when each comparison claim has "
            "product-scoped evidence."
        ),
        "recommendation": (
            "I can recommend among approved products using only verified "
            "product evidence."
        ),
    }[field]


def _safe_scope(scope: ObjectScope) -> ObjectScope:
    return ObjectScope(
        store_id=_safe_trace_value(scope.store_id),
        product_id=_safe_trace_value(scope.product_id),
        variant_id=(
            _safe_trace_value(scope.variant_id)
            if scope.variant_id is not None
            else None
        ),
    )


def _chunk_is_admitted_for_locale(
    chunk, *, field: str, scope: ObjectScope, locale: str
) -> bool:
    """Reject known non-US evidence without weakening legacy fixtures.

    Older in-repository fixtures intentionally omit applicability metadata.  A
    mounted corpus that declares language/market metadata must satisfy the
    US-English boundary; missing metadata remains a fail-closed gap only for
    claims that explicitly declare a regional or Variant-specific requirement.
    """

    if locale.casefold() != "en-us":
        return True
    metadata = chunk.metadata
    language = metadata.get("language")
    if language is not None and not language.casefold().startswith("en"):
        return False
    if field not in {"package_list", "policy"}:
        return True
    applicability = metadata.get("applicability") or metadata.get("market")
    if applicability is None:
        return True
    if "us" not in applicability.casefold():
        return False
    if field == "package_list" and chunk.variant_id is not None:
        return chunk.variant_id == scope.variant_id
    return True


def _safe_trace_value(value: str) -> str:
    if _SENSITIVE_TRACE_VALUE.search(value):
        return "[REDACTED]"
    return value


__all__ = ["ProductRagApplicationService", "ProductRagQuestionInterpreter"]
