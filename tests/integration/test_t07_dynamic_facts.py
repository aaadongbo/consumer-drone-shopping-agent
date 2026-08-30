"""T07 integration gates for current dynamic facts and safe consistency fallback."""

import json
from datetime import UTC, datetime

import pytest

from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    AttributeStatus,
    AttributeValue,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    InternalDiagnosticCode,
    PageContext,
    ToolResult,
    ToolStatus,
    TraceEventType,
    TraceOperation,
    TurnRequest,
)
from backend.shopify.fixture import DeterministicShopifyFixture

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 13, 30, tzinfo=UTC)


def _request(
    question: str = "这款现在多少钱？",
    *,
    store_id: str = "store-drone-cn",
    product_id: str = "drone-mini",
    variant_id: str | None = "mini-standard",
) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=store_id,
        conversation=ConversationRef(
            conversation_id="conversation-t07",
            message_id="message-t07",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(product_id=product_id, variant_id=variant_id),
    )


def _service(shopify, sink: InMemoryTraceSink, correlation: str = "correlation-t07"):
    return Slice1ApplicationService(
        shopify=shopify,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=sink,
        correlation_id_factory=lambda: correlation,
        clock=lambda: NOW,
    )


def test_current_dynamic_price_carries_tool_observation_through_answer() -> None:
    fixture = DeterministicShopifyFixture(clock=lambda: NOW)
    sink = InMemoryTraceSink()

    envelope = _service(fixture, sink).answer(_request())
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.claims[0].field == "price"
    assert payload.claims[0].fact.value == 2999
    assert payload.claims[0].fact.observed_at == NOW
    assert payload.evidence[0].field_locator == "commerce.price"
    assert payload.evidence[0].observed_at == NOW
    assert payload.evidence[0].fact.observed_at == NOW
    assert payload.freshness is not None
    assert payload.freshness.observed_at == NOW
    assert payload.freshness.source == payload.evidence[0].source
    assert [entry.operation for entry in fixture.call_ledger] == [
        TraceOperation.REFRESH_COMMERCE_STATE
    ]
    assert fixture.write_call_count == 0


class _MissingObservedAtPort:
    def get_products(self, *, store_id: str, product_id: str):
        raise AssertionError("T07 dynamic scenario must not read products")

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ):
        raise AssertionError("T07 dynamic scenario must not read variants")

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ):
        fact = AttributeValue(
            status=AttributeStatus.KNOWN,
            value=2999,
            unit="CNY",
            source_ref="controlled://commerce#price",
        )
        return ToolResult.model_construct(
            status=ToolStatus.SUCCESS,
            data={"price": fact},
            source="controlled://commerce",
            observed_at=None,
            retryable=False,
            error_code=None,
            missing_fields=[],
        )


def test_missing_dynamic_observed_at_returns_safe_consistency_fallback() -> None:
    sink = InMemoryTraceSink()

    envelope = _service(_MissingObservedAtPort(), sink).answer(_request())
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root
    trace_json = json.dumps([event.to_wire() for event in sink.events])

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR
    assert payload.fallback.retryable is False
    assert payload.text == "暂时无法可靠确认该商品事实，请停止展示该结论并联系支持。"
    assert payload.fallback.next_actions == ["停止展示该结论", "联系支持"]
    assert payload.claims == payload.evidence == payload.bindings == []
    assert "DYNAMIC_FACT_FRESHNESS_MISSING" not in payload.to_wire_json()
    assert InternalDiagnosticCode.DYNAMIC_FACT_FRESHNESS_MISSING.value in trace_json
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.SHOPIFY_READ_CALLED,
        TraceEventType.TOOL_RESULT,
        TraceEventType.EVIDENCE_REJECTED,
        TraceEventType.FALLBACK_PRODUCED,
    ]


def test_trace_contains_allowlisted_fields_only_and_redacts_sensitive_ids() -> None:
    sink = InMemoryTraceSink()
    service = _service(
        DeterministicShopifyFixture(clock=lambda: NOW),
        sink,
        correlation="Authorization: Bearer super-secret",
    )

    envelope = service.answer(
        _request(
            "请推荐一款适合旅行的无人机。",
            store_id="token=super-secret",
            product_id="api_key=hidden",
            variant_id="secret-variant",
        )
    )
    payload = envelope.root
    trace_json = json.dumps([event.to_wire() for event in sink.events])

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert "super-secret" not in trace_json
    assert "hidden" not in trace_json
    assert "secret-variant" not in trace_json
    assert "user_text" not in trace_json
    assert "api_key" not in trace_json
    assert all(
        set(event.model_fields_set)
        == {
            "schema_version",
            "correlation_id",
            "event_type",
            "occurred_at",
            "summary",
        }
        for event in sink.events
    )
