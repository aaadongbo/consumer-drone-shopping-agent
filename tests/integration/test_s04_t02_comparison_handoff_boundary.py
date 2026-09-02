"""S04-T02 validates S03 comparison handoff before downstream comparison work."""

from datetime import UTC, datetime

import pytest

from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.common import ObjectScope
from backend.conversation import (
    ComparisonFallbackReason,
    ComparisonMember,
    ComparisonScopeStatus,
    ComparisonSetResolver,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
    TypedHandoffRouter,
)

pytestmark = pytest.mark.integration


def resolver() -> ComparisonSetResolver:
    snapshot = DeterministicCatalogFixture(
        observed_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    ).load_store(store_id=PRIMARY_STORE_ID)
    return ComparisonSetResolver(
        snapshot=snapshot, catalog_revision="catalog-s04-fixture-v1"
    )


def member(product_id: str, variant_id: str | None) -> ComparisonMember:
    return ComparisonMember(
        scope=ObjectScope(
            store_id=PRIMARY_STORE_ID,
            product_id=product_id,
            variant_id=variant_id,
        ),
        provenance=ResolutionSource.EXPLICIT,
    )


def test_typed_handoff_materializes_only_after_bounded_variant_validation() -> None:
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            member("drone-travel", "travel-lite"),
            member("drone-travel", "travel-pack"),
        ),
    )
    handoff = TypedHandoffRouter().route(
        TargetResolution(turn_target=target, context_action="KEEP")
    )

    result = resolver().materialize(
        target=handoff.target,
        correlation_id="cmp-s04-t02-handoff",
    )

    assert result.status is ComparisonScopeStatus.READY
    assert result.comparison_set is not None
    assert result.comparison_set.correlation_id == "cmp-s04-t02-handoff"


def test_product_only_handoff_fails_before_catalog_fact_or_dynamic_reads() -> None:
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            member("drone-travel", None),
            member("drone-travel", "travel-pack"),
        ),
    )

    result = resolver().materialize(
        target=target,
        correlation_id="cmp-s04-t02-product-only",
    )

    assert result.status is ComparisonScopeStatus.NEEDS_CLARIFICATION
    assert result.comparison_set is None
    assert result.fallback_reason is ComparisonFallbackReason.PRODUCT_ONLY_REFERENCE
