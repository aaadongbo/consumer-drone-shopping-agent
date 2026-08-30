"""Unit coverage for T04's deliberately fixed application behavior."""

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
    FieldScope,
    PageContext,
    RouteAction,
    RouteIntent,
    ToolResult,
    ToolStatus,
    TraceEventType,
    TurnRequest,
    VariantRecord,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


def _request(
    *, user_text: str = "这个套装有几块电池？", variant_id: str | None = "mini-standard"
) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t04",
            message_id="message-t04",
        ),
        user_text=user_text,
        locale="zh-CN",
        page_context=PageContext(
            product_id="drone-mini",
            variant_id=variant_id,
        ),
    )


def _variant(
    *,
    store_id: str = "store-drone-cn",
    product_id: str = "drone-mini",
    variant_id: str = "mini-standard",
    attributes: dict[str, AttributeValue] | None = None,
) -> VariantRecord:
    return VariantRecord(
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        display_label="Standard Combo",
        options={"bundle": "standard"},
        variant_attributes=attributes
        if attributes is not None
        else {
            "battery_count": AttributeValue(
                status=AttributeStatus.KNOWN,
                value=1,
                unit="battery",
                source_ref="fixture://variant#battery_count",
            )
        },
    )


def _success(variants: list[VariantRecord]) -> ToolResult[list[VariantRecord]]:
    return ToolResult[list[VariantRecord]](
        status=ToolStatus.SUCCESS,
        data=variants,
        source="fixture://store-drone-cn/products/drone-mini/variants/mini-standard",
        observed_at=NOW,
        retryable=False,
    )


class _StubShopifyPort:
    def __init__(self, result: ToolResult[list[VariantRecord]]) -> None:
        self.result = result
        self.variant_calls = 0

    def get_products(self, *, store_id: str, product_id: str) -> ToolResult:
        raise AssertionError("T04 must not call get_products")

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ) -> ToolResult[list[VariantRecord]]:
        self.variant_calls += 1
        return self.result

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult:
        raise AssertionError("T04 must not call refresh_commerce_state")


def _service(
    result: ToolResult[list[VariantRecord]],
) -> tuple[Slice1ApplicationService, _StubShopifyPort, InMemoryTraceSink]:
    port = _StubShopifyPort(result)
    sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=port,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=sink,
        correlation_id_factory=lambda: "correlation-t04",
        clock=lambda: NOW,
    )
    return service, port, sink


def test_interpreter_preserves_fixed_variant_battery_route() -> None:
    decision = DeterministicQuestionInterpreter().interpret(_request())

    assert decision.intent is RouteIntent.PRODUCT_QA
    assert decision.action is RouteAction.READ_VARIANT_FACT
    assert decision.requested_field == "battery_count"
    assert decision.field_scope is FieldScope.VARIANT_SPECIFIC
    assert decision.resolved_scope.to_wire() == {
        "store_id": "store-drone-cn",
        "product_id": "drone-mini",
        "variant_id": "mini-standard",
    }


@pytest.mark.parametrize(
    "turn_request",
    [
        _request(user_text="这个套装价格多少？"),
    ],
)
def test_interpreter_rejects_unrecognized_question(
    turn_request: TurnRequest,
) -> None:
    with pytest.raises(RuntimeError):
        DeterministicQuestionInterpreter().interpret(turn_request)


def test_product_only_variant_question_does_not_claim_resolved_context() -> None:
    service, port, sink = _service(_success([_variant()]))

    payload = service.answer(_request(variant_id=None)).root

    assert port.variant_calls == 0
    assert payload.outcome.value == "FALLBACK"
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.FALLBACK_PRODUCED,
    ]


def _partial_result() -> ToolResult[list[VariantRecord]]:
    return ToolResult[list[VariantRecord]](
        status=ToolStatus.PARTIAL,
        data=[_variant()],
        source="fixture://store-drone-cn/products/drone-mini/variants/mini-standard",
        observed_at=NOW,
        retryable=True,
        missing_fields=["variant_attributes.battery_count"],
    )


@pytest.mark.parametrize(
    ("result", "reason_code"),
    [
        (_partial_result(), FallbackReasonCode.TOOL_PARTIAL_RESULT),
        (
            _success([_variant(attributes={})]),
            FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
        ),
        (
            _success(
                [
                    _variant(
                        attributes={
                            "battery_count": AttributeValue(
                                status=AttributeStatus.UNKNOWN,
                                source_ref="fixture://variant#battery_count",
                            )
                        }
                    )
                ]
            ),
            FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
        ),
    ],
    ids=[
        "non-success",
        "missing-field",
        "unknown-field",
    ],
)
def test_application_fails_closed_with_t06_fallback(
    result: ToolResult, reason_code: FallbackReasonCode
) -> None:
    service, port, sink = _service(result)

    payload = service.answer(_request()).root

    assert port.variant_calls == 1
    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is reason_code
    assert payload.claims == []
    assert payload.evidence == []
    assert payload.bindings == []
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }
    assert TraceEventType.EVIDENCE_ACCEPTED not in {
        event.event_type for event in sink.events
    }


def test_claim_and_evidence_reuse_the_tool_result_fact_without_rewriting() -> None:
    fact = AttributeValue(
        status=AttributeStatus.KNOWN,
        value=7,
        unit="battery",
        source_ref="fixture://current-tool-result#battery_count",
    )
    result = _success([_variant(attributes={"battery_count": fact})])
    service, _, _ = _service(result)

    payload = service.answer(_request()).root

    assert payload.claims[0].fact == fact
    assert payload.evidence[0].fact == fact
    assert payload.claims[0].fact == payload.evidence[0].fact
    assert payload.text == "这个套装有 7 块电池。"
