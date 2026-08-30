"""Contract checks specific to T04's application boundary."""

import inspect
from datetime import UTC, datetime

import pytest

from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
    slice_1,
)
from backend.common import SCHEMA_VERSION, ConversationRef, PageContext, TurnRequest
from backend.shopify.fixture import DeterministicShopifyFixture
from backend.shopify.port import ShopifyReadPort

pytestmark = pytest.mark.contract


def test_application_declares_port_dependency_without_constructing_fixture() -> None:
    signature = inspect.signature(Slice1ApplicationService.__init__)

    assert signature.parameters["shopify"].annotation is ShopifyReadPort
    assert "DeterministicShopifyFixture" not in inspect.getsource(slice_1)


def test_generated_answer_round_trips_through_public_wire_contract() -> None:
    now = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)
    fixture = DeterministicShopifyFixture(clock=lambda: now)
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "correlation-t04-contract",
        clock=lambda: now,
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

    assert envelope.model_validate_json(envelope.to_wire_json()) == envelope
