"""S02-T06 deterministic recommendation walking-skeleton integration tests."""

from datetime import UTC, datetime

import pytest

from backend.agent import Slice2RecommendationService, Slice2TraceSink
from backend.catalog import CatalogFixtureSnapshot, DeterministicCatalogFixture
from backend.catalog.fixture import (
    ISOLATION_STORE_ID,
    PRIMARY_STORE_ID,
    CommerceState,
    VariantCommerceSnapshot,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    AttributeValue,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    PageContext,
    ToolResult,
    ToolStatus,
    TraceEventType,
    TurnRequest,
)

pytestmark = pytest.mark.integration

OBSERVED_AT = datetime(2026, 8, 31, 15, 0, tzinfo=UTC)
CORRELATION_ID = "correlation-s02-t06"


class CountingCatalog:
    def __init__(self, snapshot: CatalogFixtureSnapshot) -> None:
        self._snapshot = snapshot
        self.reads = 0
        self.write_call_count = 0

    def load_store(self, *, store_id: str) -> CatalogFixtureSnapshot:
        self.reads += 1
        assert store_id == self._snapshot.store_id
        return self._snapshot


class LeakyCatalog:
    def __init__(self, snapshot: CatalogFixtureSnapshot) -> None:
        self._snapshot = snapshot
        self.write_call_count = 0

    def load_store(self, *, store_id: str) -> CatalogFixtureSnapshot:
        assert store_id != self._snapshot.store_id
        return self._snapshot


def _snapshot(store_id: str = PRIMARY_STORE_ID) -> CatalogFixtureSnapshot:
    return DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=store_id
    )


def _service(
    catalog: CountingCatalog,
) -> tuple[Slice2RecommendationService, Slice2TraceSink]:
    sink = Slice2TraceSink()
    return (
        Slice2RecommendationService(
            catalog=catalog,
            trace_sink=sink,
            correlation_id_factory=lambda: CORRELATION_ID,
            clock=lambda: OBSERVED_AT,
        ),
        sink,
    )


def _request(
    text: str,
    *,
    store_id: str = PRIMARY_STORE_ID,
    product_id: str = "drone-travel",
) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=store_id,
        conversation=ConversationRef(
            conversation_id="conversation-s02-t06",
            message_id="message-s02-t06",
        ),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id=product_id),
    )


def test_single_turn_recommendation_returns_top_candidate_with_evidence() -> None:
    catalog = CountingCatalog(_snapshot())
    service, sink = _service(catalog)

    envelope = service.answer(
        _request(
            "请推荐一款适合旅行的无人机，预算 3000 元，重量 250g 以内，至少1块电池，4K"
        )
    )
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope.store_id == PRIMARY_STORE_ID
    assert payload.resolved_scope.product_id == "drone-travel"
    assert payload.resolved_scope.variant_id == "travel-lite"
    assert payload.product_card is not None
    assert payload.product_card.product_id == "drone-travel"
    assert payload.product_card.variant_id == "travel-lite"
    assert "Northwind Travel" in payload.text
    assert "travel-lite" in payload.text
    assert payload.claims
    assert payload.evidence
    assert payload.bindings
    assert payload.freshness is not None
    assert payload.freshness.observed_at == OBSERVED_AT
    assert {item.variant_id for item in payload.evidence} == {"travel-lite"}
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
    assert TraceEventType.ANSWER_PRODUCED in {event.event_type for event in sink.events}
    assert catalog.reads == 1
    assert catalog.write_call_count == 0


def test_no_match_falls_back_without_recommendation_claims() -> None:
    catalog = CountingCatalog(_snapshot())
    service, sink = _service(catalog)

    payload = service.answer(_request("预算 1000 元以内，至少3块电池，适合旅行")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.FACT_UNKNOWN_OR_MISSING
    assert payload.claims == payload.evidence == payload.bindings == []
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }
    assert catalog.write_call_count == 0


def test_unsupported_input_falls_back_without_catalog_read() -> None:
    catalog = CountingCatalog(_snapshot())
    service, sink = _service(catalog)

    payload = service.answer(_request("你喜欢什么颜色？")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.OUT_OF_SCOPE
    assert payload.claims == payload.evidence == payload.bindings == []
    assert catalog.reads == 0
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }


def test_store_isolation_uses_only_requested_store() -> None:
    catalog = CountingCatalog(_snapshot(ISOLATION_STORE_ID))
    service, _sink = _service(catalog)

    payload = service.answer(
        _request(
            "请推荐一款适合旅行的无人机，预算 3000 元，至少1块电池",
            store_id=ISOLATION_STORE_ID,
        )
    ).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope.store_id == ISOLATION_STORE_ID
    assert payload.resolved_scope.product_id == "drone-travel"
    assert payload.resolved_scope.variant_id == "travel-lite"
    assert payload.product_card is not None
    assert payload.product_card.display_title == "Contoso Travel"
    assert all(item.store_id == ISOLATION_STORE_ID for item in payload.evidence)
    assert catalog.write_call_count == 0


def test_mismatched_provider_snapshot_fails_closed_without_leaking_candidates() -> None:
    catalog = LeakyCatalog(_snapshot(PRIMARY_STORE_ID))
    service, sink = _service(catalog)

    payload = service.answer(
        _request(
            "请推荐一款适合旅行的无人机，预算 3000 元，至少1块电池",
            store_id=ISOLATION_STORE_ID,
        )
    ).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.PRODUCT_NOT_FOUND
    assert payload.resolved_scope.store_id == ISOLATION_STORE_ID
    assert payload.claims == payload.evidence == payload.bindings == []
    assert "Northwind Travel" not in payload.text
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }
    assert catalog.write_call_count == 0


def test_partial_commerce_fails_closed_without_recommendation_claims() -> None:
    catalog = CountingCatalog(_partial_commerce_snapshot())
    service, sink = _service(catalog)

    payload = service.answer(_request("预算 3000 元以内，适合旅行")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.FACT_UNKNOWN_OR_MISSING
    assert payload.claims == payload.evidence == payload.bindings == []
    assert {event.summary.tool_status for event in sink.events} >= {ToolStatus.PARTIAL}
    assert catalog.write_call_count == 0


def _partial_commerce_snapshot() -> CatalogFixtureSnapshot:
    snapshot = _snapshot()
    partial_commerce = tuple(
        VariantCommerceSnapshot(
            store_id=entry.store_id,
            product_id=entry.product_id,
            variant_id=entry.variant_id,
            result=ToolResult[CommerceState](
                status=ToolStatus.PARTIAL,
                data={
                    "availability": AttributeValue(
                        status=entry.result.data["availability"].status,
                        value=entry.result.data["availability"].value,
                        source_ref=entry.result.data["availability"].source_ref,
                        observed_at=OBSERVED_AT,
                    )
                },
                source=entry.result.source,
                observed_at=OBSERVED_AT,
                retryable=True,
                missing_fields=["price"],
            ),
        )
        for entry in snapshot.commerce
        if entry.result.data is not None
    )
    return CatalogFixtureSnapshot(
        store_id=snapshot.store_id,
        products=snapshot.products,
        variants=snapshot.variants,
        commerce=partial_commerce,
    )
