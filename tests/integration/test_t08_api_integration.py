"""T08 integration gate for API -> application -> deterministic fixture."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.api import create_conversation_api
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
    PageContext,
    TraceOperation,
    TurnRequest,
)
from backend.shopify import DeterministicShopifyFixture

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 14, 10, tzinfo=UTC)


def test_conversation_api_reaches_application_and_read_only_fixture() -> None:
    fixture = DeterministicShopifyFixture(clock=lambda: NOW)
    sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=sink,
        correlation_id_factory=lambda: "correlation-t08-integration",
        clock=lambda: NOW,
    )
    request = TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t08-integration",
            message_id="message-t08-integration",
        ),
        user_text="这款现在多少钱？",
        locale="zh-CN",
        page_context=PageContext(
            product_id="drone-mini",
            variant_id="mini-standard",
        ),
    )

    response = TestClient(create_conversation_api(service)).post(
        "/v1/conversation/turn",
        json=request.to_wire(),
    )
    payload = AnswerEnvelope.model_validate(response.json()).root

    assert response.status_code == 200
    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.claims[0].field == "price"
    assert payload.claims[0].fact.value == 2999
    assert payload.trace_correlation_id == "correlation-t08-integration"
    assert {event.correlation_id for event in sink.events} == {
        payload.trace_correlation_id
    }
    assert [entry.operation for entry in fixture.call_ledger] == [
        TraceOperation.REFRESH_COMMERCE_STATE
    ]
    assert fixture.write_call_count == 0
