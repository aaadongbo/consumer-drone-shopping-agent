"""S02-T06 recommendation walking skeleton through the existing HTTP boundary."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.agent import Slice2RecommendationService, Slice2TraceSink
from backend.api import MinimalConversationClient, create_conversation_api
from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    PageContext,
    TurnRequest,
)

pytestmark = pytest.mark.e2e

OBSERVED_AT = datetime(2026, 8, 31, 15, 30, tzinfo=UTC)
CORRELATION_ID = "correlation-s02-t06-e2e"


def _client() -> tuple[MinimalConversationClient, Slice2TraceSink]:
    sink = Slice2TraceSink()
    service = Slice2RecommendationService(
        catalog=DeterministicCatalogFixture(observed_at=OBSERVED_AT),
        trace_sink=sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: OBSERVED_AT,
    )
    transport = TestClient(create_conversation_api(service))
    return MinimalConversationClient(transport), sink


def _request(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=PRIMARY_STORE_ID,
        conversation=ConversationRef(
            conversation_id="conversation-s02-t06-e2e",
            message_id="message-s02-t06-e2e",
        ),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )


def test_recommendation_api_returns_answer_envelope() -> None:
    client, sink = _client()

    payload = client.ask(
        _request(
            "请推荐一款适合旅行的无人机，预算 3000 元，重量 250g 以内，至少1块电池"
        )
    ).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.trace_correlation_id == CORRELATION_ID
    assert payload.product_card is not None
    assert payload.product_card.product_id == "drone-travel"
    assert payload.product_card.variant_id == "travel-lite"
    assert payload.claims
    assert payload.evidence
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}


def test_recommendation_api_returns_safe_fallback_for_no_match() -> None:
    client, sink = _client()

    payload = client.ask(_request("预算 1000 元以内，至少3块电池，适合旅行")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.FACT_UNKNOWN_OR_MISSING
    assert payload.claims == payload.evidence == payload.bindings == []
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
