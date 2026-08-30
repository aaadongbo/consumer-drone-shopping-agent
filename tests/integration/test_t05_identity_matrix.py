"""T05 application-boundary Matrix #2 through #5."""

from collections import Counter
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
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    PageContext,
    TraceEventType,
    TraceOperation,
    TurnRequest,
)
from backend.shopify.fixture import DeterministicShopifyFixture

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 11, 30, tzinfo=UTC)
CORRELATION_ID = "correlation-t05-matrix"


def _request(
    question: str,
    *,
    product_id: str = "drone-mini",
    variant_id: str | None = None,
) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t05-matrix",
            message_id="message-t05-matrix",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(product_id=product_id, variant_id=variant_id),
    )


def _system() -> tuple[
    Slice1ApplicationService, DeterministicShopifyFixture, InMemoryTraceSink
]:
    fixture = DeterministicShopifyFixture(clock=lambda: NOW)
    sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: NOW,
    )
    return service, fixture, sink


def test_matrix_2_product_shared_fact_is_strictly_product_scoped() -> None:
    service, fixture, sink = _system()

    envelope = service.answer(_request("这款无人机的制造商是谁？"))
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope.to_wire() == {
        "store_id": "store-drone-cn",
        "product_id": "drone-mini",
    }
    assert payload.product_card is None
    assert payload.text == "这款无人机的制造商是 Aero Labs。"
    assert len(payload.claims) == len(payload.evidence) == len(payload.bindings) == 1
    claim = payload.claims[0]
    evidence = payload.evidence[0]
    binding = payload.bindings[0]
    assert claim.field == "manufacturer"
    assert claim.fact.value == "Aero Labs"
    assert claim.fact == evidence.fact
    assert evidence.observed_at == NOW
    assert evidence.variant_id is None
    assert evidence.field_locator == "shared_attributes.manufacturer"
    assert binding.claim_id == claim.claim_id
    assert binding.evidence_ids == [evidence.evidence_id]
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
    assert TraceEventType.PAGE_CONTEXT_RESOLVED in {
        event.event_type for event in sink.events
    }
    _assert_calls(fixture, get_products=1)


def test_matrix_3_product_only_variant_fact_returns_variant_required() -> None:
    service, fixture, sink = _system()

    envelope = service.answer(_request("这个套装有几块电池？"))
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    _assert_fallback(payload, FallbackReasonCode.VARIANT_REQUIRED)
    assert any("Variant" in action for action in payload.fallback.next_actions)
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.FALLBACK_PRODUCED,
    ]
    _assert_calls(fixture)


def test_matrix_4_missing_product_returns_product_not_found() -> None:
    service, fixture, sink = _system()

    envelope = service.answer(
        _request("这款无人机的制造商是谁？", product_id="missing-product")
    )
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    _assert_fallback(payload, FallbackReasonCode.PRODUCT_NOT_FOUND)
    assert any(
        "商品页" in action or "重新选择商品" in action
        for action in payload.fallback.next_actions
    )
    _assert_identity_failure_trace(sink)
    _assert_calls(fixture, get_products=1)


@pytest.mark.parametrize("variant_id", ["missing-variant", "cine-standard"])
def test_matrix_5_missing_or_foreign_variant_returns_variant_not_found(
    variant_id: str,
) -> None:
    service, fixture, sink = _system()

    envelope = service.answer(
        _request(
            "这个套装有几块电池？",
            product_id="drone-mini",
            variant_id=variant_id,
        )
    )
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    _assert_fallback(payload, FallbackReasonCode.VARIANT_NOT_FOUND)
    assert any("有效 Variant" in action for action in payload.fallback.next_actions)
    _assert_identity_failure_trace(sink)
    _assert_calls(fixture, get_variants=1)


def test_explicit_explorer_variant_does_not_reuse_standard_variant_fact() -> None:
    service, fixture, _ = _system()

    payload = service.answer(
        _request("这个套装有几块电池？", variant_id="mini-explorer")
    ).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.claims[0].fact.value == 3
    assert payload.claims[0].fact == payload.evidence[0].fact
    assert payload.resolved_scope.variant_id == "mini-explorer"
    assert payload.evidence[0].variant_id == "mini-explorer"
    _assert_calls(fixture, get_variants=1)


def _assert_fallback(payload, reason: FallbackReasonCode) -> None:
    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.product_card is None
    assert payload.claims == []
    assert payload.evidence == []
    assert payload.bindings == []
    assert payload.fallback.reason_code is reason
    assert payload.fallback.retryable is False
    assert payload.fallback.next_actions
    assert payload.trace_correlation_id == CORRELATION_ID


def _assert_identity_failure_trace(sink: InMemoryTraceSink) -> None:
    event_types = {event.event_type for event in sink.events}
    assert TraceEventType.FALLBACK_PRODUCED in event_types
    assert TraceEventType.PAGE_CONTEXT_RESOLVED not in event_types
    assert TraceEventType.EVIDENCE_ACCEPTED not in event_types
    assert TraceEventType.ANSWER_PRODUCED not in event_types
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}


def _assert_calls(
    fixture: DeterministicShopifyFixture,
    *,
    get_products: int = 0,
    get_variants: int = 0,
    refresh_commerce_state: int = 0,
) -> None:
    counts = Counter(entry.operation for entry in fixture.call_ledger)
    assert counts[TraceOperation.GET_PRODUCTS] == get_products
    assert counts[TraceOperation.GET_VARIANTS] == get_variants
    assert counts[TraceOperation.REFRESH_COMMERCE_STATE] == refresh_commerce_state
    assert fixture.write_call_count == 0
