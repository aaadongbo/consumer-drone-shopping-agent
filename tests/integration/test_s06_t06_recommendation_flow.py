"""Integration coverage for the Slice 6 recommendation walking skeleton."""

from datetime import UTC, datetime

import pytest

from backend.application import MultiProductRecommendationService
from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    PageContext,
    ToolResult,
    TurnRequest,
)
from backend.shopify import CommerceState

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 3, tzinfo=UTC)
_STORE_ID = "store-s02-alpha"


class CatalogCommerceReadDouble:
    """Test-only read port backed by the deterministic Slice 2 catalog fixture."""

    def __init__(self) -> None:
        self.snapshot: CatalogFixtureSnapshot = DeterministicCatalogFixture(
            observed_at=_NOW
        ).load_store(store_id=_STORE_ID)
        self.calls: list[tuple[str, str, str]] = []
        self.writes = 0

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult[CommerceState]:
        self.calls.append((store_id, product_id, variant_id))
        for item in self.snapshot.commerce:
            if (item.store_id, item.product_id, item.variant_id) == (
                store_id,
                product_id,
                variant_id,
            ):
                return item.result
        raise AssertionError("refresh crossed the catalog identity boundary")


def _request(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=_STORE_ID,
        conversation=ConversationRef(conversation_id="s06-flow", message_id=text),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )


def _service(port: CatalogCommerceReadDouble) -> MultiProductRecommendationService:
    return MultiProductRecommendationService(
        catalog=DeterministicCatalogFixture(observed_at=_NOW),
        shopify=port,
        correlation_id_factory=lambda: "s06-flow-trace",
        clock=lambda: _NOW,
    )


def test_flow_returns_at_most_three_candidates_with_current_commerce() -> None:
    port = CatalogCommerceReadDouble()
    result = _service(port).recommend(_request("预算 6000 元，适合旅行"))

    assert result.fallback is None
    assert 1 <= len(result.candidates) <= 3
    product_ids = {item.candidate.product_id for item in result.candidates}
    assert len(product_ids) == len(result.candidates)
    assert "drone-travel" in product_ids
    assert len(port.calls) == len(result.candidates)
    assert port.writes == 0
    assert all(event.correlation_id == result.correlation_id for event in result.trace)
    for candidate in result.candidates:
        assert candidate.evidence_bundle.candidate == candidate.candidate
        assert candidate.explanation.explanation is not None
        assert candidate.evidence_bundle.derived_evidence


def test_no_match_produces_fallback_without_formal_candidates() -> None:
    port = CatalogCommerceReadDouble()
    result = _service(port).recommend(_request("预算 1 元"))

    assert result.candidates == ()
    assert result.fallback is not None
    assert result.fallback.reason.value == "NO_MATCH"
    assert result.trace[-1].event_type.value == "FALLBACK"
    assert port.writes == 0
