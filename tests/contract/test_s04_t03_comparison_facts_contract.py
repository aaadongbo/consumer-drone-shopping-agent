"""S04-T03 comparison fact and evidence binding contracts."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.common import AttributeStatus, ObjectScope
from backend.conversation import (
    ComparisonScopeStatus,
    ComparisonSetResolver,
    ResolutionSource,
)
from backend.conversation.target_resolution import (
    ComparisonMember,
    TurnTarget,
    TurnTargetKind,
)
from backend.evidence import (
    ComparisonFact,
    build_static_comparison_facts,
)

pytestmark = pytest.mark.contract


def comparison_set():
    snapshot = DeterministicCatalogFixture(
        observed_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    ).load_store(store_id=PRIMARY_STORE_ID)
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            ComparisonMember(
                scope=ObjectScope(
                    store_id=PRIMARY_STORE_ID,
                    product_id="drone-travel",
                    variant_id="travel-lite",
                ),
                provenance=ResolutionSource.EXPLICIT,
            ),
            ComparisonMember(
                scope=ObjectScope(
                    store_id=PRIMARY_STORE_ID,
                    product_id="drone-travel",
                    variant_id="travel-pack",
                ),
                provenance=ResolutionSource.EXPLICIT,
            ),
        ),
    )
    result = ComparisonSetResolver(
        snapshot=snapshot,
        catalog_revision="catalog-s04-fixture-v1",
    ).materialize(target=target, correlation_id="cmp-s04-t03")
    assert result.comparison_set is not None
    return snapshot, result.comparison_set


def test_fact_set_round_trip_preserves_member_owned_bindings() -> None:
    snapshot, comparison = comparison_set()
    facts = build_static_comparison_facts(
        comparison_set=comparison,
        snapshot=snapshot,
        field_keys=("battery_count", "takeoff_weight", "obstacle_sensing"),
    )

    restored = facts.model_validate_json(facts.to_wire_json())

    assert restored == facts
    assert {fact.member_id for fact in restored.facts} == {"member-1", "member-2"}
    for fact in restored.facts:
        assert fact.binding.member_id == fact.member_id
        assert (
            fact.binding.scope == comparison.members[int(fact.member_id[-1]) - 1].scope
        )
        assert fact.binding.source_class == "CATALOG"


def test_unknown_and_not_applicable_remain_distinct_fact_states() -> None:
    snapshot, comparison = comparison_set()
    facts = build_static_comparison_facts(
        comparison_set=comparison,
        snapshot=snapshot,
        field_keys=("obstacle_sensing", "interchangeable_lens"),
    )

    states = {(fact.member_id, fact.field_key): fact.state for fact in facts.facts}

    assert states[("member-1", "obstacle_sensing")] is AttributeStatus.UNKNOWN
    assert states[("member-1", "interchangeable_lens")] is (
        AttributeStatus.NOT_APPLICABLE
    )


def test_wrong_member_evidence_binding_is_rejected() -> None:
    snapshot, comparison = comparison_set()
    facts = build_static_comparison_facts(
        comparison_set=comparison,
        snapshot=snapshot,
        field_keys=("battery_count",),
    )
    first = facts.facts[0]

    with pytest.raises(ValidationError, match="match the fact member"):
        ComparisonFact(
            comparison_fact_id=first.comparison_fact_id,
            member_id=first.member_id,
            field_key=first.field_key,
            fact=first.fact,
            state=first.state,
            source_class=first.source_class,
            catalog_revision=first.catalog_revision,
            binding=first.binding.model_copy(update={"member_id": "other-member"}),
        )


def test_mismatched_evidence_locator_is_rejected() -> None:
    snapshot, comparison = comparison_set()
    first = build_static_comparison_facts(
        comparison_set=comparison,
        snapshot=snapshot,
        field_keys=("battery_count",),
    ).facts[0]

    with pytest.raises(ValidationError, match="locator"):
        ComparisonFact(
            comparison_fact_id=first.comparison_fact_id,
            member_id=first.member_id,
            field_key=first.field_key,
            fact=first.fact,
            state=first.state,
            source_class=first.source_class,
            catalog_revision=first.catalog_revision,
            binding=first.binding.model_copy(
                update={"source_locator": "fixture://another-member#battery_count"}
            ),
        )


def test_non_ready_comparison_set_cannot_produce_static_facts() -> None:
    snapshot, comparison = comparison_set()
    deferred = comparison.model_copy(
        update={
            "scope_status": ComparisonScopeStatus.TYPED_DEFERRAL,
            "fallback_reason": "CROSS_PRODUCT_DEFERRED",
        }
    )

    with pytest.raises(ValueError, match="READY"):
        build_static_comparison_facts(
            comparison_set=deferred,
            snapshot=snapshot,
            field_keys=("battery_count",),
        )
