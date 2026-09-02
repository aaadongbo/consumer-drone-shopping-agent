"""S04-T04 dynamic comparison facts stay fresh, read-only, and member-scoped."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.common import (
    AttributeStatus,
    ObjectScope,
    ToolResult,
    TraceOperation,
)
from backend.conversation import (
    ComparisonSet,
    ComparisonSetMember,
    MemberProvenance,
    MemberSourceKind,
)
from backend.evidence import (
    ComparisonDegradationReason,
    ComparisonFactState,
    ComparisonFreshnessVerdict,
    build_dynamic_comparison_facts,
)
from backend.shopify import DeterministicShopifyFixture, FixtureOutcome

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
STORE_ID = "store-drone-cn"


def comparison_set() -> ComparisonSet:
    members = (
        ComparisonSetMember(
            member_id="member-1",
            scope=ObjectScope(
                store_id=STORE_ID,
                product_id="drone-mini",
                variant_id="mini-standard",
            ),
            provenance=MemberProvenance(
                source_kind=MemberSourceKind.EXPLICIT,
                original_reference="drone-mini/mini-standard",
                resolver_outcome="variant_handoff_validated",
            ),
            resolution_reason="validated comparison member",
            catalog_revision="catalog-s04-fixture-v1",
            display_name="Aero Mini / Standard Combo",
        ),
        ComparisonSetMember(
            member_id="member-2",
            scope=ObjectScope(
                store_id=STORE_ID,
                product_id="drone-mini",
                variant_id="mini-explorer",
            ),
            provenance=MemberProvenance(
                source_kind=MemberSourceKind.EXPLICIT,
                original_reference="drone-mini/mini-explorer",
                resolver_outcome="variant_handoff_validated",
            ),
            resolution_reason="validated comparison member",
            catalog_revision="catalog-s04-fixture-v1",
            display_name="Aero Mini / Explorer Combo",
        ),
    )
    return ComparisonSet(
        correlation_id="cmp-s04-t04",
        store_id=STORE_ID,
        members=members,
    )


def fixture(
    *,
    observed_at: datetime = NOW,
    outcome: FixtureOutcome | None = None,
) -> DeterministicShopifyFixture:
    forced = {} if outcome is None else {TraceOperation.REFRESH_COMMERCE_STATE: outcome}
    return DeterministicShopifyFixture(
        clock=lambda: observed_at,
        forced_outcomes=forced,
    )


def facts_by_key(facts):
    return {(fact.member_id, fact.field_key): fact for fact in facts.facts}


def test_current_dynamic_reads_are_member_scoped_and_fresh() -> None:
    shopify = fixture()

    facts = build_dynamic_comparison_facts(
        comparison_set=comparison_set(),
        shopify=shopify,
        now=NOW,
    )
    by_key = facts_by_key(facts)

    assert by_key[("member-1", "price")].fact.value == 2999
    assert by_key[("member-2", "price")].fact.value == 4399
    assert by_key[("member-1", "inventory")].fact.value == 12
    assert by_key[("member-2", "inventory")].fact.value == 0
    assert by_key[("member-1", "availability")].fact.value is True
    assert by_key[("member-2", "availability")].fact.value is False
    assert all(
        fact.state is AttributeStatus.KNOWN
        and fact.freshness is not None
        and fact.freshness.verdict is ComparisonFreshnessVerdict.FRESH
        and fact.freshness.observed_at == NOW
        for fact in facts.facts
    )
    assert {
        (fact.member_id, fact.binding.scope.variant_id) for fact in facts.facts
    } == {
        ("member-1", "mini-standard"),
        ("member-2", "mini-explorer"),
    }
    assert [entry.variant_id for entry in shopify.call_ledger] == [
        "mini-standard",
        "mini-explorer",
    ]
    assert shopify.write_call_count == 0


def test_stale_dynamic_reads_are_unavailable_without_stale_values() -> None:
    facts = build_dynamic_comparison_facts(
        comparison_set=comparison_set(),
        shopify=fixture(observed_at=NOW - timedelta(minutes=6)),
        now=NOW,
    )

    assert len(facts.facts) == 6
    assert all(
        fact.state is ComparisonFactState.UNAVAILABLE
        and fact.fact.status is AttributeStatus.UNKNOWN
        and fact.fact.value is None
        and fact.degradation_reason is ComparisonDegradationReason.STALE_RESULT
        and fact.freshness is not None
        and fact.freshness.verdict is ComparisonFreshnessVerdict.STALE
        for fact in facts.facts
    )


def test_failed_dynamic_reads_are_unavailable_and_do_not_write() -> None:
    shopify = fixture(outcome=FixtureOutcome.TIMEOUT)

    facts = build_dynamic_comparison_facts(
        comparison_set=comparison_set(),
        shopify=shopify,
        now=NOW,
    )

    assert all(
        fact.state is ComparisonFactState.UNAVAILABLE
        and fact.degradation_reason is ComparisonDegradationReason.READ_ERROR
        and fact.freshness is not None
        and fact.freshness.verdict is ComparisonFreshnessVerdict.UNAVAILABLE
        for fact in facts.facts
    )
    assert shopify.write_call_count == 0


class MismatchedSourcePort:
    def __init__(self) -> None:
        self._fixture = fixture()

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult:
        wrong_variant_id = (
            "mini-explorer" if variant_id == "mini-standard" else "mini-standard"
        )
        return self._fixture.refresh_commerce_state(
            store_id=store_id,
            product_id=product_id,
            variant_id=wrong_variant_id,
        )


def test_mismatched_tool_result_identity_is_unavailable() -> None:
    facts = build_dynamic_comparison_facts(
        comparison_set=comparison_set(),
        shopify=MismatchedSourcePort(),
        now=NOW,
    )

    assert all(
        fact.state is ComparisonFactState.UNAVAILABLE
        and fact.degradation_reason is ComparisonDegradationReason.IDENTITY_MISMATCH
        and fact.fact.value is None
        for fact in facts.facts
    )


class MismatchedFieldLocatorPort:
    def __init__(self) -> None:
        self._fixture = fixture()

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult:
        result = self._fixture.refresh_commerce_state(
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
        )
        assert result.data is not None
        data = dict(result.data)
        data["price"] = data["inventory"]
        return result.model_copy(update={"data": data})


def test_mismatched_dynamic_field_locator_is_unavailable() -> None:
    facts = build_dynamic_comparison_facts(
        comparison_set=comparison_set(),
        shopify=MismatchedFieldLocatorPort(),
        now=NOW,
        field_keys=("price",),
    )

    assert len(facts.facts) == 2
    assert all(
        fact.state is ComparisonFactState.UNAVAILABLE
        and fact.degradation_reason is ComparisonDegradationReason.IDENTITY_MISMATCH
        and fact.fact.value is None
        for fact in facts.facts
    )


def test_partial_dynamic_result_only_exposes_present_fields() -> None:
    facts = build_dynamic_comparison_facts(
        comparison_set=comparison_set(),
        shopify=fixture(outcome=FixtureOutcome.PARTIAL),
        now=NOW,
    )
    by_key = facts_by_key(facts)

    assert by_key[("member-1", "price")].state is AttributeStatus.KNOWN
    assert by_key[("member-1", "inventory")].state is AttributeStatus.KNOWN
    assert by_key[("member-1", "availability")].state is ComparisonFactState.UNAVAILABLE
    assert (
        by_key[("member-1", "availability")].degradation_reason
        is ComparisonDegradationReason.PARTIAL_RESULT
    )
