"""T04 Matrix #1: explicit Variant and one known static fact."""

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
    ConversationRef,
    EnvelopeOutcome,
    PageContext,
    TraceEventType,
    TraceOperation,
    TurnRequest,
)
from backend.shopify.fixture import DeterministicShopifyFixture

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 9, 30, tzinfo=UTC)
CORRELATION_ID = "correlation-t04-happy-path"


def test_explicit_variant_battery_count_happy_path() -> None:
    fixture = DeterministicShopifyFixture(clock=lambda: NOW)
    trace_sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=trace_sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: NOW,
    )
    request = TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t04",
            message_id="message-t04",
        ),
        user_text="这个套装有几块电池？",
        locale="zh-CN",
        page_context=PageContext(
            product_id="drone-mini",
            variant_id="mini-standard",
        ),
    )

    envelope = service.answer(request)
    restored = AnswerEnvelope.model_validate_json(envelope.to_wire_json())
    payload = restored.root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.trace_correlation_id == CORRELATION_ID
    assert payload.resolved_scope.to_wire() == {
        "store_id": "store-drone-cn",
        "product_id": "drone-mini",
        "variant_id": "mini-standard",
    }
    assert payload.product_card is None
    assert len(payload.claims) == len(payload.evidence) == len(payload.bindings) == 1

    claim = payload.claims[0]
    evidence = payload.evidence[0]
    binding = payload.bindings[0]
    assert claim.field == "battery_count"
    assert claim.fact.status is AttributeStatus.KNOWN
    assert claim.fact.value == 1
    assert claim.fact == evidence.fact
    assert evidence.observed_at == NOW
    assert (
        evidence.store_id,
        evidence.product_id,
        evidence.variant_id,
    ) == ("store-drone-cn", "drone-mini", "mini-standard")
    assert binding.claim_id == claim.claim_id
    assert binding.evidence_ids == [evidence.evidence_id]

    assert [event.event_type for event in trace_sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.SHOPIFY_READ_CALLED,
        TraceEventType.TOOL_RESULT,
        TraceEventType.PAGE_CONTEXT_RESOLVED,
        TraceEventType.EVIDENCE_ACCEPTED,
        TraceEventType.ANSWER_PRODUCED,
    ]
    assert {event.correlation_id for event in trace_sink.events} == {CORRELATION_ID}
    assert {event.occurred_at for event in trace_sink.events} == {NOW}
    assert all(
        set(event.to_wire())
        == {
            "schema_version",
            "correlation_id",
            "event_type",
            "occurred_at",
            "summary",
        }
        for event in trace_sink.events
    )

    assert len(fixture.call_ledger) == 1
    ledger_entry = fixture.call_ledger[0]
    assert ledger_entry.operation is TraceOperation.GET_VARIANTS
    assert (
        ledger_entry.store_id,
        ledger_entry.product_id,
        ledger_entry.variant_id,
    ) == ("store-drone-cn", "drone-mini", "mini-standard")
    assert fixture.write_call_count == 0
