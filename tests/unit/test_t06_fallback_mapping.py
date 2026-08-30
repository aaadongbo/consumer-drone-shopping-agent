"""T06 unit gates for stable fallback mapping and bounded routing."""

from datetime import UTC, datetime

import pytest

from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    AttributeStatus,
    AttributeValue,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    PageContext,
    RouteAction,
    RouteIntent,
    ToolErrorCode,
    ToolResult,
    ToolStatus,
    TraceEventType,
    TurnRequest,
    VariantRecord,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
CORRELATION_ID = "correlation-t06-unit"


def _request(question: str, *, variant_id: str | None = "mini-standard") -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t06-unit",
            message_id="message-t06-unit",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(
            product_id="drone-mini",
            variant_id=variant_id,
        ),
    )


def _variant(attributes: dict[str, AttributeValue]) -> VariantRecord:
    return VariantRecord(
        store_id="store-drone-cn",
        product_id="drone-mini",
        variant_id="mini-standard",
        display_label="Standard Combo",
        options={"bundle": "standard"},
        variant_attributes=attributes,
    )


def _known(value: object, field: str) -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=value,
        source_ref=f"controlled://{field}",
    )


def _error(error_code: ToolErrorCode, *, retryable: bool) -> ToolResult:
    return ToolResult(
        status=ToolStatus.ERROR,
        source="controlled://tool-error",
        observed_at=NOW,
        error_code=error_code,
        retryable=retryable,
    )


def _partial() -> ToolResult[list[VariantRecord]]:
    return ToolResult[list[VariantRecord]](
        status=ToolStatus.PARTIAL,
        data=[_variant({"battery_count": _known(1, "battery_count")})],
        source="controlled://partial",
        observed_at=NOW,
        error_code=ToolErrorCode.PARTIAL_RESULT,
        retryable=True,
        missing_fields=["variant_attributes.remote_controller"],
    )


def _success(attributes: dict[str, AttributeValue]) -> ToolResult[list[VariantRecord]]:
    return ToolResult[list[VariantRecord]](
        status=ToolStatus.SUCCESS,
        data=[_variant(attributes)],
        source="controlled://success",
        observed_at=NOW,
        retryable=False,
    )


class _ControlledShopifyPort:
    def __init__(self, variants: ToolResult | None = None) -> None:
        self.variants = variants
        self.product_calls = 0
        self.variant_calls = 0
        self.commerce_calls = 0

    def get_products(self, *, store_id: str, product_id: str) -> ToolResult:
        self.product_calls += 1
        raise AssertionError("T06 unit scenario must not read Product data")

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ) -> ToolResult:
        self.variant_calls += 1
        assert self.variants is not None
        return self.variants

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult:
        self.commerce_calls += 1
        raise AssertionError("T06 must not enter dynamic-fact implementation")


def _service(
    result: ToolResult | None = None,
) -> tuple[Slice1ApplicationService, _ControlledShopifyPort, InMemoryTraceSink]:
    port = _ControlledShopifyPort(result)
    sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=port,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: NOW,
    )
    return service, port, sink


@pytest.mark.parametrize(
    ("question", "result", "reason", "retryable", "actions"),
    [
        (
            "这个套装有几块电池？",
            _error(ToolErrorCode.TIMEOUT, retryable=True),
            FallbackReasonCode.TOOL_TIMEOUT,
            True,
            ["重试"],
        ),
        (
            "这个套装有几块电池？",
            _error(ToolErrorCode.RATE_LIMITED, retryable=True),
            FallbackReasonCode.TOOL_RATE_LIMITED,
            True,
            ["稍后重试"],
        ),
        (
            "这个套装有几块电池？",
            _error(ToolErrorCode.UNAUTHORIZED, retryable=False),
            FallbackReasonCode.TOOL_UNAUTHORIZED,
            False,
            ["联系支持或检查商店连接"],
        ),
        (
            "这个套装配遥控器吗？",
            _partial(),
            FallbackReasonCode.TOOL_PARTIAL_RESULT,
            True,
            ["重试", "询问其他可确认字段"],
        ),
    ],
)
def test_tool_result_maps_to_exact_standard_fallback(
    question: str,
    result: ToolResult,
    reason: FallbackReasonCode,
    retryable: bool,
    actions: list[str],
) -> None:
    service, port, sink = _service(result)

    payload = service.answer(_request(question)).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is reason
    assert payload.fallback.retryable is retryable
    assert payload.fallback.next_actions == actions
    assert payload.text == payload.fallback.message
    assert payload.claims == payload.evidence == payload.bindings == []
    assert (port.product_calls, port.variant_calls, port.commerce_calls) == (0, 1, 0)
    assert TraceEventType.EVIDENCE_ACCEPTED not in {
        event.event_type for event in sink.events
    }
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}


@pytest.mark.parametrize(
    "attributes",
    [
        {},
        {
            "obstacle_sensing": AttributeValue(
                status=AttributeStatus.UNKNOWN,
                source_ref="controlled://obstacle_sensing",
            )
        },
    ],
    ids=["missing", "unknown"],
)
def test_unknown_or_missing_fact_uses_non_assertive_wording(
    attributes: dict[str, AttributeValue],
) -> None:
    service, port, sink = _service(_success(attributes))

    payload = service.answer(_request("这个套装支持避障吗？")).root
    copy = f"{payload.text} {' '.join(payload.fallback.next_actions)}".casefold()

    assert payload.fallback.reason_code is FallbackReasonCode.FACT_UNKNOWN_OR_MISSING
    assert payload.fallback.retryable is False
    assert payload.fallback.next_actions == ["查看其他已知规格", "联系商家确认"]
    assert all(term not in copy for term in ("不支持", "false", " 0 "))
    assert payload.claims == payload.evidence == payload.bindings == []
    assert port.variant_calls == 1
    assert TraceEventType.PAGE_CONTEXT_RESOLVED in {
        event.event_type for event in sink.events
    }


def test_known_remote_controller_uses_its_own_answer_semantics() -> None:
    service, _, _ = _service(
        _success({"remote_controller": _known("included", "remote_controller")})
    )

    payload = service.answer(_request("这个套装配遥控器吗？")).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.text == "这个套装的遥控器配置为 included。"
    assert "电池" not in payload.text
    assert payload.claims[0].field == "remote_controller"
    assert payload.claims[0].fact.value == "included"


def test_explicit_out_of_scope_route_returns_fallback_without_shopify_call() -> None:
    request = _request("请推荐一款适合旅行的无人机。", variant_id=None)
    interpreter = DeterministicQuestionInterpreter()
    decision = interpreter.interpret(request)
    service, port, sink = _service()

    payload = service.answer(request).root

    assert decision.intent is RouteIntent.OUT_OF_SCOPE
    assert decision.action is RouteAction.RETURN_FALLBACK
    assert decision.requested_field is None
    assert decision.field_scope is None
    assert payload.fallback.reason_code is FallbackReasonCode.OUT_OF_SCOPE
    assert payload.fallback.retryable is False
    assert payload.fallback.next_actions == [
        "改问当前商品的规格",
        "联系人工渠道",
    ]
    assert (port.product_calls, port.variant_calls, port.commerce_calls) == (0, 0, 0)
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.FALLBACK_PRODUCED,
    ]


def test_unrecognized_input_does_not_open_an_agent_fallback() -> None:
    service, port, sink = _service()

    with pytest.raises(RuntimeError, match="fixed Slice 1 classifications"):
        service.answer(_request("随便聊点什么。", variant_id=None))

    assert (port.product_calls, port.variant_calls, port.commerce_calls) == (0, 0, 0)
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED
    ]
