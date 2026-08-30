"""Deterministic Slice 1 Product-fact answer and fallback paths."""

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
_OBSTACLE_SENSING_QUESTION = "这个套装支持避障吗？"
_PRICE_QUESTION = "这款现在多少钱？"
_REMOTE_CONTROLLER_QUESTION = "这个套装配遥控器吗？"
_OUT_OF_SCOPE_QUESTIONS = frozenset(
    {
        "请推荐一款适合旅行的无人机。",
        "帮我查询订单状态。",
        "无人机飞行法规是什么？",
    }
)


class _LocalNonAnswer(RuntimeError):
    """Stop a branch assigned to later tasks without manufacturing an answer."""


class DeterministicQuestionInterpreter:
    """Classify only fixed Product-fact and explicit out-of-scope samples."""

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
        if request.user_text in {
            _OBSTACLE_SENSING_QUESTION,
            _REMOTE_CONTROLLER_QUESTION,
        }:
            requested_field = (
                "obstacle_sensing"
                if request.user_text == _OBSTACLE_SENSING_QUESTION
                else "remote_controller"
            )
            action = (
                RouteAction.READ_VARIANT_FACT
                if request_scope.variant_id is not None
                else RouteAction.REQUEST_VARIANT_CLARIFICATION
            )
            return MinimalRouteDecision(
                intent=RouteIntent.PRODUCT_QA,
                action=action,
                requested_field=requested_field,
                field_scope=FieldScope.VARIANT_SPECIFIC,
                resolved_scope=request_scope,
                reason="T06 deterministic Variant-specific fallback question",
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
        if request.user_text in _OUT_OF_SCOPE_QUESTIONS:
            return MinimalRouteDecision(
                intent=RouteIntent.OUT_OF_SCOPE,
                action=RouteAction.RETURN_FALLBACK,
                resolved_scope=request_scope,
                reason="T06 explicit non-Product-Fact sample",
            )
        raise _LocalNonAnswer("Question is outside the fixed Slice 1 classifications")


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

        if decision.intent is RouteIntent.OUT_OF_SCOPE:
            return self._fallback(
                request,
                correlation_id,
                request_scope,
                FallbackReasonCode.OUT_OF_SCOPE,
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

        failure_reason = _tool_failure_reason(result)
        if failure_reason is not None:
            return self._fallback(
                request,
                correlation_id,
                scope,
                failure_reason,
            )
        if result.status is not ToolStatus.SUCCESS or result.data is None:
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
        if fact is None or fact.status is AttributeStatus.UNKNOWN:
            return self._fallback(
                request,
                correlation_id,
                scope,
                FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
            )
        if fact.status is not AttributeStatus.KNOWN:
            raise _LocalNonAnswer("Product shared fact is not applicable")
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

        failure_reason = _tool_failure_reason(result)
        if failure_reason is not None:
            return self._fallback(
                request,
                correlation_id,
                scope,
                failure_reason,
            )
        if result.status is not ToolStatus.SUCCESS or result.data is None:
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
        if fact is None or fact.status is AttributeStatus.UNKNOWN:
            return self._fallback(
                request,
                correlation_id,
                scope,
                FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
            )
        if fact.status is not AttributeStatus.KNOWN:
            raise _LocalNonAnswer("Variant fact is not applicable")
        return self._answer_from_fact(
            request=request,
            correlation_id=correlation_id,
            scope=scope,
            requested_field=requested_field,
            fact=fact,
            source=result.source,
            observed_at=result.observed_at,
            field_locator=f"variant_attributes.{requested_field}",
            text=_variant_fact_text(requested_field, fact),
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


def _variant_fact_text(requested_field: str, fact: AttributeValue) -> str:
    if requested_field == "battery_count":
        return f"这个套装有 {fact.value} 块电池。"
    if requested_field == "obstacle_sensing":
        return f"这个套装的避障规格为 {fact.value}。"
    if requested_field == "remote_controller":
        return f"这个套装的遥控器配置为 {fact.value}。"
    raise _LocalNonAnswer("Variant fact has no approved answer template")


def _fallback_copy(
    reason_code: FallbackReasonCode,
) -> tuple[str, bool, tuple[str, ...]]:
    return {
        FallbackReasonCode.VARIANT_REQUIRED: (
            "该信息取决于具体 Variant，请先选择或提供具体 Variant。",
            False,
            ("选择或提供具体 Variant",),
        ),
        FallbackReasonCode.PRODUCT_NOT_FOUND: (
            "未在当前商店中找到该商品。",
            False,
            ("返回商品页或重新选择商品",),
        ),
        FallbackReasonCode.VARIANT_NOT_FOUND: (
            "未找到属于当前商品的该 Variant。",
            False,
            ("重新选择有效 Variant",),
        ),
        FallbackReasonCode.FACT_UNKNOWN_OR_MISSING: (
            "当前授权数据无法确认该项事实。",
            False,
            ("查看其他已知规格", "联系商家确认"),
        ),
        FallbackReasonCode.TOOL_TIMEOUT: (
            "读取当前商品信息超时，请重试。",
            True,
            ("重试",),
        ),
        FallbackReasonCode.TOOL_RATE_LIMITED: (
            "当前读取请求过于频繁，请稍后重试。",
            True,
            ("稍后重试",),
        ),
        FallbackReasonCode.TOOL_UNAUTHORIZED: (
            "暂时无法读取当前商店信息。",
            False,
            ("联系支持或检查商店连接",),
        ),
        FallbackReasonCode.TOOL_PARTIAL_RESULT: (
            "本次只返回了部分商品信息，无法确认所请求的事实。",
            True,
            ("重试", "询问其他可确认字段"),
        ),
        FallbackReasonCode.OUT_OF_SCOPE: (
            "该请求不属于当前商品事实查询范围。",
            False,
            ("改问当前商品的规格", "联系人工渠道"),
        ),
    }[reason_code]


def _tool_failure_reason(result: ToolResult) -> FallbackReasonCode | None:
    if result.status is ToolStatus.PARTIAL:
        return FallbackReasonCode.TOOL_PARTIAL_RESULT
    if result.status is not ToolStatus.ERROR:
        return None
    return {
        ToolErrorCode.TIMEOUT: FallbackReasonCode.TOOL_TIMEOUT,
        ToolErrorCode.RATE_LIMITED: FallbackReasonCode.TOOL_RATE_LIMITED,
        ToolErrorCode.UNAUTHORIZED: FallbackReasonCode.TOOL_UNAUTHORIZED,
        ToolErrorCode.PRODUCT_NOT_FOUND: FallbackReasonCode.PRODUCT_NOT_FOUND,
        ToolErrorCode.VARIANT_NOT_FOUND: FallbackReasonCode.VARIANT_NOT_FOUND,
    }.get(result.error_code)


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
