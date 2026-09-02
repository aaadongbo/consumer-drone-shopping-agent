"""S04-T02 bounded comparison member validation."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import ISOLATION_STORE_ID, PRIMARY_STORE_ID
from backend.common import ObjectScope
from backend.conversation import (
    ComparisonFallbackReason,
    ComparisonMember,
    ComparisonScopeStatus,
    ComparisonSetResolver,
    MemberSourceKind,
    ResolutionSource,
    TurnTarget,
    TurnTargetKind,
)

pytestmark = pytest.mark.unit


def resolver() -> ComparisonSetResolver:
    snapshot = DeterministicCatalogFixture(
        observed_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    ).load_store(store_id=PRIMARY_STORE_ID)
    return ComparisonSetResolver(
        snapshot=snapshot, catalog_revision="catalog-s04-fixture-v1"
    )


def member(
    product_id: str,
    variant_id: str | None,
    *,
    store_id: str = PRIMARY_STORE_ID,
    source: ResolutionSource = ResolutionSource.EXPLICIT,
) -> ComparisonMember:
    return ComparisonMember(
        scope=ObjectScope(
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
        ),
        provenance=source,
    )


def target(*members: ComparisonMember) -> TurnTarget:
    return TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=members,
    )


def test_same_product_explicit_and_confirmed_variants_materialize_ready_set() -> None:
    result = resolver().materialize(
        target=target(
            member("drone-travel", "travel-lite"),
            member(
                "drone-travel",
                "travel-pack",
                source=ResolutionSource.CONFIRMED_CONTEXT,
            ),
        ),
        correlation_id="cmp-s04-t02-ready",
        confirmed_context_revision=8,
    )

    assert result.status is ComparisonScopeStatus.READY
    assert result.comparison_set is not None
    assert [item.scope.variant_id for item in result.comparison_set.members] == [
        "travel-lite",
        "travel-pack",
    ]
    assert [item.provenance.source_kind for item in result.comparison_set.members] == [
        MemberSourceKind.EXPLICIT,
        MemberSourceKind.CONFIRMED_CONTEXT,
    ]
    assert result.comparison_set.members[1].provenance.context_revision == 8


@pytest.mark.parametrize(
    ("members", "reason"),
    [
        (
            (member("drone-travel", None), member("drone-travel", "travel-pack")),
            ComparisonFallbackReason.PRODUCT_ONLY_REFERENCE,
        ),
        (
            (
                member("drone-travel", "travel-lite", store_id=ISOLATION_STORE_ID),
                member("drone-travel", "travel-pack"),
            ),
            ComparisonFallbackReason.CROSS_STORE,
        ),
        (
            (
                member("drone-travel", "cinema-pro"),
                member("drone-travel", "travel-pack"),
            ),
            ComparisonFallbackReason.OWNERSHIP_MISMATCH,
        ),
        (
            (
                member("drone-travel", "missing-variant"),
                member("drone-travel", "travel-pack"),
            ),
            ComparisonFallbackReason.MEMBER_UNRESOLVED,
        ),
    ],
)
def test_invalid_members_fail_closed_before_fact_reads(
    members: tuple[ComparisonMember, ...], reason: ComparisonFallbackReason
) -> None:
    result = resolver().materialize(
        target=target(*members),
        correlation_id="cmp-s04-t02-invalid",
    )

    assert result.status is ComparisonScopeStatus.NEEDS_CLARIFICATION
    assert result.comparison_set is None
    assert result.fallback_reason is reason


def test_duplicate_members_fail_closed_at_handoff_shape_boundary() -> None:
    with pytest.raises(ValidationError, match="members must be unique"):
        target(
            member("drone-travel", "travel-lite"),
            member("drone-travel", "travel-lite"),
        )


def test_page_context_cannot_supply_comparison_membership() -> None:
    result = resolver().materialize(
        target=target(
            member(
                "drone-travel",
                "travel-lite",
                source=ResolutionSource.PAGE_CONTEXT,
            ),
            member("drone-travel", "travel-pack"),
        ),
        correlation_id="cmp-s04-t02-page",
    )

    assert result.status is ComparisonScopeStatus.NEEDS_CLARIFICATION
    assert result.fallback_reason is ComparisonFallbackReason.MEMBER_UNRESOLVED
    assert "explicit or confirmed" in (result.clarification_reason or "")


def test_cross_product_set_gets_typed_deferral_not_comparison_ready() -> None:
    result = resolver().materialize(
        target=target(
            member("drone-travel", "travel-lite"),
            member("drone-cinema", "cinema-pro"),
        ),
        correlation_id="cmp-s04-t02-cross-product",
    )

    assert result.status is ComparisonScopeStatus.TYPED_DEFERRAL
    assert result.fallback_reason is ComparisonFallbackReason.CROSS_PRODUCT_DEFERRED
    assert result.comparison_set is not None
    assert result.comparison_set.scope_status is ComparisonScopeStatus.TYPED_DEFERRAL
