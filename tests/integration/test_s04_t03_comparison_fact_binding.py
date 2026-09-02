"""S04-T03 static comparison facts stay bound to their owning members."""

from datetime import UTC, datetime

import pytest

from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.common import ObjectScope
from backend.conversation import ComparisonSetResolver, ResolutionSource
from backend.conversation.target_resolution import (
    ComparisonMember,
    TurnTarget,
    TurnTargetKind,
)
from backend.evidence import build_static_comparison_facts

pytestmark = pytest.mark.integration


def test_catalog_fact_builder_never_reuses_another_members_scope() -> None:
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
    resolution = ComparisonSetResolver(
        snapshot=snapshot,
        catalog_revision="catalog-s04-fixture-v1",
    ).materialize(target=target, correlation_id="cmp-s04-t03-integration")
    assert resolution.comparison_set is not None

    facts = build_static_comparison_facts(
        comparison_set=resolution.comparison_set,
        snapshot=snapshot,
        field_keys=("battery_count", "takeoff_weight"),
    )

    fact_scopes = {
        (fact.member_id, fact.binding.scope.variant_id) for fact in facts.facts
    }
    assert ("member-1", "travel-lite") in fact_scopes
    assert ("member-2", "travel-pack") in fact_scopes
    assert ("member-1", "travel-pack") not in fact_scopes
    assert ("member-2", "travel-lite") not in fact_scopes
