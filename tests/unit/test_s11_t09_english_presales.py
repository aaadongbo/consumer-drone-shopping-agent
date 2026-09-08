"""T09 deterministic English routing and pre-sales boundary tests."""

from datetime import UTC, datetime

import pytest

from backend.application.slice_1 import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    EnvelopeOutcome,
    PageContext,
    RouteAction,
    RouteIntent,
    TurnRequest,
)
from backend.shopify import DeterministicShopifyFixture

pytestmark = pytest.mark.unit


def _request(text: str, *, variant_id: str | None = "mini-standard") -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(conversation_id="t09", message_id=text),
        user_text=text,
        locale="en-US",
        page_context=PageContext(product_id="drone-mini", variant_id=variant_id),
    )


def test_english_commerce_and_variant_questions_are_bounded() -> None:
    interpreter = DeterministicQuestionInterpreter()
    price = interpreter.interpret(_request("What is the current price?"))
    battery = interpreter.interpret(_request("How many batteries are in the package?"))

    assert price.action is RouteAction.READ_VARIANT_FACT
    assert price.requested_field == "price"
    assert battery.action is RouteAction.READ_VARIANT_FACT
    assert battery.requested_field == "battery_count"


def test_english_order_and_payment_questions_are_store_support_handoffs() -> None:
    interpreter = DeterministicQuestionInterpreter()
    for text in ("Where is my order?", "Can I get a refund?", "My payment failed"):
        decision = interpreter.interpret(_request(text))
        assert decision.intent is RouteIntent.OUT_OF_SCOPE
        assert decision.action is RouteAction.RETURN_FALLBACK


def test_english_dynamic_answer_is_read_only_and_localized() -> None:
    fixture = DeterministicShopifyFixture(
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC)
    )
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-correlation",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )

    payload = service.answer(_request("What is the current price?")).root
    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.text.startswith("The current price")
    assert fixture.write_call_count == 0


def test_product_only_english_variant_question_fails_closed() -> None:
    decision = DeterministicQuestionInterpreter().interpret(
        _request("How many batteries are in the package?", variant_id=None)
    )
    assert decision.action is RouteAction.REQUEST_VARIANT_CLARIFICATION
