"""T09 actual application-path English acceptance fixtures."""

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
    TurnRequest,
)
from backend.shopify import DeterministicShopifyFixture

pytestmark = pytest.mark.integration


def _request(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(conversation_id="t09-flow", message_id=text),
        user_text=text,
        locale="en-US",
        page_context=PageContext(product_id="drone-mini", variant_id="mini-standard"),
    )


def test_application_path_answers_price_and_handoffs_order_questions() -> None:
    fixture = DeterministicShopifyFixture(
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC)
    )
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-flow-correlation",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )
    answer = service.answer(_request("How much does this cost?")).root
    handoff = service.answer(_request("Where is my order?")).root
    assert answer.outcome is EnvelopeOutcome.ANSWER
    assert "current price" in answer.text
    assert handoff.outcome is EnvelopeOutcome.FALLBACK
    assert "orders" in handoff.text
    assert fixture.write_call_count == 0
