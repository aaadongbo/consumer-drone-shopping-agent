"""E2E-style replay of the internal Slice 6 multi-product journey."""

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

pytestmark = pytest.mark.e2e

_NOW = datetime(2026, 9, 3, tzinfo=UTC)
_STORE_ID = "store-s02-alpha"


class _ReadOnlyCatalogCommerce:
    def __init__(self) -> None:
        self.snapshot: CatalogFixtureSnapshot = DeterministicCatalogFixture(
            observed_at=_NOW
        ).load_store(store_id=_STORE_ID)
        self.write_calls = 0

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult[CommerceState]:
        for item in self.snapshot.commerce:
            if (item.store_id, item.product_id, item.variant_id) == (
                store_id,
                product_id,
                variant_id,
            ):
                return item.result
        raise AssertionError("unknown candidate refresh")


def test_recommendation_journey_replays_identity_and_derived_bindings() -> None:
    port = _ReadOnlyCatalogCommerce()
    request = TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=_STORE_ID,
        conversation=ConversationRef(
            conversation_id="s06-e2e", message_id="recommend-travel"
        ),
        user_text="预算 6000 元，适合旅行",
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )
    result = MultiProductRecommendationService(
        catalog=DeterministicCatalogFixture(observed_at=_NOW),
        shopify=port,
        correlation_id_factory=lambda: "s06-e2e-trace",
        clock=lambda: _NOW,
    ).recommend(request)

    assert result.fallback is None
    for candidate in result.candidates:
        scope = candidate.evidence_bundle.candidate
        assert all(
            item.candidate == scope
            for item in candidate.evidence_bundle.catalog_evidence
        )
        assert all(
            item.candidate == scope
            for item in candidate.evidence_bundle.commerce_evidence
        )
        assert all(
            item.candidate == scope
            for item in candidate.evidence_bundle.derived_evidence
        )
        for derived in candidate.evidence_bundle.derived_evidence:
            all_ids = {
                item.evidence_id
                for item in (
                    *candidate.evidence_bundle.catalog_evidence,
                    *candidate.evidence_bundle.commerce_evidence,
                    *candidate.evidence_bundle.rag_evidence,
                )
            }
            assert set(derived.input_evidence_ids) <= all_ids
    assert port.write_calls == 0
