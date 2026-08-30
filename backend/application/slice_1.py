"""Deterministic Slice 1 Product/Variant identity application paths."""

from collections.abc import Callable
from datetime import datetime

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
    FieldScope,
    MinimalRouteDecision,
    ObjectScope,
    ProductRecord,
    RouteAction,
    RouteIntent,
    StandardFallback,
    ToolErrorCode,
    ToolResult,
    ToolStatus,
    TraceEvent,
    TraceEventType,
    TraceOperation,
    TraceResult,
    TraceSummary,
    TurnRequest,
    VariantRecord,
)
from backend.shopify.port import ShopifyReadPort

_BATTERY_QUESTION = "这个套装有几块电池？"
_MANUFACTURER_QUESTION = "这款无人机的制造商是谁？"
_PRICE_QUESTION = "这款现在多少钱？"


class _LocalNonAnswer(RuntimeError):
    """Stop a branch assigned to later tasks without manufacturing an answer."""


class DeterministicQuestionInterpreter:
    """Classify only the three fixed Slice 1 questions implemented through T05."""

    def interpret(self, request: TurnRequest) -> MinimalRouteDecision:
        request_scope = _request_scope(request)
        if request.user_text == _MANUFACTURER_QUESTION:
            return MinimalRouteDecision(
                intent=RouteIntent.PRODUCT_QA,
                action=RouteAction.READ_PRODUCT_FACT,
                requested_field="manufacturer",
                field_scope=FieldScope.PRODUCT_SHARED,
                resolved_scope=_product_scope(request_scope),
                reason="T05 deterministic Product-shared manufacturer question",
            )
        if request.user_text == _BATTERY_QUESTION:
            action = (
                RouteAction.READ_VARIANT_FACT
                if request_scope.variant_id is not None
                else RouteAction.REQUEST_VARIANT_CLARIFICATION
            )
            return MinimalRouteDecision(
                intent=RouteIntent.PRODUCT_QA,
                action=action,
                requested_field="battery_count",
                field_scope=FieldScope.VARIANT_SPECIFIC,
                resolved_scope=request_scope,
                reason="T05 deterministic Variant-specific battery question",
            )
        if request.user_text == _PRICE_QUESTION:
            return MinimalRouteDecision(
                intent=RouteIntent.PRODUCT_QA,
                action=RouteAction.READ_VARIANT_FACT,
                requested_field="price",
                field_scope=FieldScope.DYNAMIC_VARIANT,
                resolved_scope=request_scope,
                reason="T05 deterministic dynamic Variant price classification",
            )
        raise _LocalNonAnswer("Question is outside the fixed T05 classifications")


class InMemoryTraceSink:
    """Keep only validated, summary-only Trace Contract events in memory."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def append(self, event: TraceEvent) -> None:
        self._events.append(event)


class Slice1ApplicationService:
    """Answer fixed static facts after exact identity resolution."""

    def __init__(
        self,
        *,
        shopify: ShopifyReadPort,
        interpreter: DeterministicQuestionInterpreter,
        trace_sink: InMemoryTraceSink,
        correlation_id_factory: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        self._shopify = shopify
        self._interpreter = interpreter
        self._trace_sink = trace_sink
        self._correlation_id_factory = correlation_id_factory
        self._clock = clock

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        correlation_id = self._correlation_id_factory()
        request_scope = _request_scope(request)
        self._trace(
            correlation_id,
            TraceEventType.TURN_REQUEST_ACCEPTED,
            TraceResult.ACCEPTED,
            scope=request_scope,
        )

        decision = self._interpreter.interpret(request)
        self._trace(
            correlation_id,
            TraceEventType.ROUTE_DECISION,
            TraceResult.SUCCESS,
            scope=decision.resolved_scope,
        )

        if (
            decision.field_scope
            in {FieldScope.VARIANT_SPECIFIC, FieldScope.DYNAMIC_VARIANT}
            and request_scope.variant_id is None
        ):
            return self._fallback(
                request,
                correlation_id,
                request_scope,
                FallbackReasonCode.VARIANT_REQUIRED,
            )
        if decision.field_scope is FieldScope.PRODUCT_SHARED:
            return self._answer_product_fact(request, correlation_id, decision)
        if decision.field_scope is FieldScope.DYNAMIC_VARIANT:
            raise _LocalNonAnswer("Dynamic commerce reads are outside T05")
        return self._answer_variant_fact(request, correlation_id, decision)

    def _answer_product_fact(
        self,
        request: TurnRequest,
        correlation_id: str,
        decision: MinimalRouteDecision,
    ) -> AnswerEnvelope:
        scope = decision.resolved_scope
        self._trace_read_call(correlation_id, scope, TraceOperation.GET_PRODUCTS)
        result = self._shopify.get_products(
            store_id=scope.store_id,
            product_id=scope.product_id,
        )
        self._trace_tool_result(
            correlation_id, scope, TraceOperation.GET_PRODUCTS, result
        )

        if result.status is not ToolStatus.SUCCESS or result.data is None:
            if (
                result.status is ToolStatus.ERROR
                and result.error_code is ToolErrorCode.PRODUCT_NOT_FOUND
            ):
                return self._fallback(
                    request,
                    correlation_id,
                    scope,
                    FallbackReasonCode.PRODUCT_NOT_FOUND,
                )
            raise _LocalNonAnswer("Product read did not succeed")

        product = _exact_product(result.data, scope)
        if product is None:
            return self._fallback(
                request,
                correlation_id,
                scope,
                FallbackReasonCode.PRODUCT_NOT_FOUND,
            )
        self._trace_page_context_resolved(correlation_id, scope)

        requested_field = _required_requested_field(decision)
        fact = product.shared_attributes.get(requested_field)
        if fact is None or fact.status is not AttributeStatus.KNOWN:
            raise _LocalNonAnswer("Product shared fact is not known")
        return self._answer_from_fact(
            request=request,
            correlation_id=correlation_id,
            scope=scope,
            requested_field=requested_field,
            fact=fact,
            source=result.source,
            observed_at=result.observed_at,
            field_locator=f"shared_attributes.{requested_field}",
            text=f"这款无人机的制造商是 {fact.value}。",
        )

    def _answer_variant_fact(
        self,
        request: TurnRequest,
        correlation_id: str,
        decision: MinimalRouteDecision,
    ) -> AnswerEnvelope:
        scope = decision.resolved_scope
        if scope.variant_id is None:
            raise _LocalNonAnswer("Variant fact requires a Variant identity")
        self._trace_read_call(correlation_id, scope, TraceOperation.GET_VARIANTS)
        result = self._shopify.get_variants(
            store_id=scope.store_id,
            product_id=scope.product_id,
            variant_id=scope.variant_id,
        )
        self._trace_tool_result(
            correlation_id, scope, TraceOperation.GET_VARIANTS, result
        )

        if result.status is not ToolStatus.SUCCESS or result.data is None:
            if result.status is ToolStatus.ERROR and result.error_code in {
                ToolErrorCode.PRODUCT_NOT_FOUND,
                ToolErrorCode.VARIANT_NOT_FOUND,
            }:
                reason_code = (
                    FallbackReasonCode.PRODUCT_NOT_FOUND
                    if result.error_code is ToolErrorCode.PRODUCT_NOT_FOUND
                    else FallbackReasonCode.VARIANT_NOT_FOUND
                )
                return self._fallback(
                    request,
                    correlation_id,
                    scope,
                    reason_code,
                )
            raise _LocalNonAnswer("Variant read did not succeed")

        variant = _exact_variant(result.data, scope)
        if variant is None:
            return self._fallback(
                request,
                correlation_id,
                scope,
                FallbackReasonCode.VARIANT_NOT_FOUND,
            )
        self._trace_page_context_resolved(correlation_id, scope)

        requested_field = _required_requested_field(decision)
        fact = variant.variant_attributes.get(requested_field)
        if fact is None or fact.status is not AttributeStatus.KNOWN:
            raise _LocalNonAnswer("Variant fact is not known")
        return self._answer_from_fact(
            request=request,
            correlation_id=correlation_id,
            scope=scope,
            requested_field=requested_field,
            fact=fact,
            source=result.source,
            observed_at=result.observed_at,
            field_locator=f"variant_attributes.{requested_field}",
            text=f"这个套装有 {fact.value} 块电池。",
        )

    def _answer_from_fact(
        self,
        *,
        request: TurnRequest,
        correlation_id: str,
        scope: ObjectScope,
        requested_field: str,
        fact: AttributeValue,
        source: str,
        observed_at: datetime,
        field_locator: str,
        text: str,
    ) -> AnswerEnvelope:
        claim_id = f"claim-{requested_field.replace('_', '-')}"
        evidence_id = f"evidence-{requested_field.replace('_', '-')}"
        evidence = Evidence(
            evidence_id=evidence_id,
            type=EvidenceType.TOOL,
            store_id=scope.store_id,
            product_id=scope.product_id,
            variant_id=scope.variant_id,
            field_locator=field_locator,
            fact=fact,
            source=source,
            observed_at=observed_at,
        )
        self._trace(
            correlation_id,
            TraceEventType.EVIDENCE_ACCEPTED,
            TraceResult.ACCEPTED,
            scope=scope,
        )

        payload = AnswerPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.ANSWER,
            conversation=request.conversation,
            trace_correlation_id=correlation_id,
            resolved_scope=scope,
            text=text,
            claims=[Claim(claim_id=claim_id, field=requested_field, fact=fact)],
            evidence=[evidence],
            bindings=[
                ClaimEvidenceBinding(
                    claim_id=claim_id,
                    evidence_ids=[evidence_id],
                )
            ],
        )
        _require_answer_integrity(payload)
        envelope = AnswerEnvelope(root=payload)
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
        message, next_action = _fallback_copy(reason_code)
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
                retryable=False,
                next_actions=[next_action],
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

    def _trace_page_context_resolved(
        self, correlation_id: str, scope: ObjectScope
    ) -> None:
        self._trace(
            correlation_id,
            TraceEventType.PAGE_CONTEXT_RESOLVED,
            TraceResult.SUCCESS,
            scope=scope,
        )

    def _trace_read_call(
        self,
        correlation_id: str,
        scope: ObjectScope,
        operation: TraceOperation,
    ) -> None:
        self._trace(
            correlation_id,
            TraceEventType.SHOPIFY_READ_CALLED,
            TraceResult.ACCEPTED,
            scope=scope,
            operation=operation,
        )

    def _trace_tool_result(
        self,
        correlation_id: str,
        scope: ObjectScope,
        operation: TraceOperation,
        result: ToolResult,
    ) -> None:
        self._trace(
            correlation_id,
            TraceEventType.TOOL_RESULT,
            _trace_result(result.status),
            scope=scope,
            operation=operation,
            tool_status=result.status,
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
                correlation_id=correlation_id,
                event_type=event_type,
                occurred_at=self._clock(),
                summary=TraceSummary(
                    result=result,
                    scope=scope,
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


def _product_scope(scope: ObjectScope) -> ObjectScope:
    return ObjectScope(store_id=scope.store_id, product_id=scope.product_id)


def _exact_product(
    products: list[ProductRecord], scope: ObjectScope
) -> ProductRecord | None:
    if len(products) != 1:
        return None
    product = products[0]
    if (product.store_id, product.product_id) != (scope.store_id, scope.product_id):
        return None
    return product


def _exact_variant(
    variants: list[VariantRecord], scope: ObjectScope
) -> VariantRecord | None:
    if len(variants) != 1:
        return None
    variant = variants[0]
    if (variant.store_id, variant.product_id, variant.variant_id) != (
        scope.store_id,
        scope.product_id,
        scope.variant_id,
    ):
        return None
    return variant


def _required_requested_field(decision: MinimalRouteDecision) -> str:
    if decision.requested_field is None:
        raise _LocalNonAnswer("PRODUCT_QA route omitted its requested field")
    return decision.requested_field


def _fallback_copy(reason_code: FallbackReasonCode) -> tuple[str, str]:
    return {
        FallbackReasonCode.VARIANT_REQUIRED: (
            "该信息取决于具体 Variant，请先选择或提供具体 Variant。",
            "选择或提供具体 Variant",
        ),
        FallbackReasonCode.PRODUCT_NOT_FOUND: (
            "未在当前商店中找到该商品。",
            "返回商品页或重新选择商品",
        ),
        FallbackReasonCode.VARIANT_NOT_FOUND: (
            "未找到属于当前商品的该 Variant。",
            "重新选择有效 Variant",
        ),
    }[reason_code]


def _require_answer_integrity(payload: AnswerPayload) -> None:
    evidence_by_id = {item.evidence_id: item for item in payload.evidence}
    bindings_by_claim: dict[str, list[ClaimEvidenceBinding]] = {}
    for binding in payload.bindings:
        bindings_by_claim.setdefault(binding.claim_id, []).append(binding)

    expected_identity = (
        payload.resolved_scope.store_id,
        payload.resolved_scope.product_id,
        payload.resolved_scope.variant_id,
    )
    for claim in payload.claims:
        claim_bindings = bindings_by_claim.get(claim.claim_id, [])
        if len(claim_bindings) != 1:
            raise _LocalNonAnswer("Claim must have exactly one binding")
        evidence_ids = claim_bindings[0].evidence_ids
        if len(evidence_ids) != 1 or evidence_ids[0] not in evidence_by_id:
            raise _LocalNonAnswer("Binding must identify exactly one existing evidence")
        bound_evidence = evidence_by_id[evidence_ids[0]]
        if bound_evidence.fact != claim.fact:
            raise _LocalNonAnswer("Claim and Evidence facts differ")
        if (
            bound_evidence.store_id,
            bound_evidence.product_id,
            bound_evidence.variant_id,
        ) != expected_identity:
            raise _LocalNonAnswer("Evidence identity differs from answer scope")


def _trace_result(status: ToolStatus) -> TraceResult:
    return {
        ToolStatus.SUCCESS: TraceResult.SUCCESS,
        ToolStatus.PARTIAL: TraceResult.PARTIAL,
        ToolStatus.ERROR: TraceResult.ERROR,
    }[status]
