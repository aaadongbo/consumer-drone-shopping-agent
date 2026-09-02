"""Integration coverage for read-only commerce refresh and HARD recheck."""

from datetime import UTC, datetime

import pytest

from backend.catalog.commerce_refresh import refresh_and_recheck_candidate
from backend.common import ToolStatus, TraceOperation, VariantRecord
from backend.shopify import DeterministicShopifyFixture, FixtureOutcome

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 3, tzinfo=UTC)
_STORE_ID = "store-drone-cn"


def _variant() -> VariantRecord:
    result = DeterministicShopifyFixture(clock=lambda: _NOW).get_variants(
        store_id=_STORE_ID,
        product_id="drone-mini",
        variant_id="mini-standard",
    )
    assert result.data is not None
    return result.data[0]


def test_refresh_uses_current_tool_result_and_rechecks_variant() -> None:
    shopify = DeterministicShopifyFixture(clock=lambda: _NOW)
    outcome = refresh_and_recheck_candidate(shopify=shopify, variant=_variant())

    assert outcome.result.status is ToolStatus.SUCCESS
    assert outcome.result.observed_at == _NOW
    assert outcome.eligibility.eligible is True
    assert {item.field for item in outcome.evidence} >= {
        "price",
        "inventory",
        "availability",
    }
    assert [entry.operation for entry in shopify.call_ledger] == [
        TraceOperation.REFRESH_COMMERCE_STATE,
    ]
    assert shopify.write_call_count == 0


def test_refresh_failure_cannot_reuse_old_commerce_facts() -> None:
    shopify = DeterministicShopifyFixture(
        clock=lambda: _NOW,
        forced_outcomes={TraceOperation.REFRESH_COMMERCE_STATE: FixtureOutcome.TIMEOUT},
    )
    outcome = refresh_and_recheck_candidate(shopify=shopify, variant=_variant())

    assert outcome.result.status is ToolStatus.ERROR
    assert outcome.result.error_code.value == "TIMEOUT"
    assert outcome.evidence == ()
    assert outcome.eligibility.eligible is False
    assert shopify.write_call_count == 0
