"""S03-T03 exact store-scoped explicit-reference resolution tests."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    CatalogAlias,
    CatalogReferenceResolver,
    DeterministicCatalogFixture,
    ExplicitReference,
    ReferenceClarificationReason,
    ReferenceResolutionStatus,
)
from backend.catalog.fixture import ISOLATION_STORE_ID, PRIMARY_STORE_ID
from backend.common import ObjectScope

pytestmark = pytest.mark.unit

OBSERVED_AT = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)


def resolver(store_id: str = PRIMARY_STORE_ID, aliases=()):
    snapshot = DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=store_id
    )
    return CatalogReferenceResolver(snapshot=snapshot, aliases=aliases)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        (
            ExplicitReference(product_name=" northwind   travel "),
            ("drone-travel", None),
        ),
        (ExplicitReference(variant_name="Pro Kit"), ("drone-cinema", "cinema-pro")),
        (
            ExplicitReference(product_name="drone-travel", variant_name="Lite Combo"),
            ("drone-travel", "travel-lite"),
        ),
    ],
)
def test_exact_names_resolve_to_one_store_owned_identity(reference, expected) -> None:
    result = resolver().resolve(reference)

    assert result.status is ReferenceResolutionStatus.RESOLVED
    assert result.scope is not None
    assert (result.scope.product_id, result.scope.variant_id) == expected


def test_controlled_alias_resolves_without_fuzzy_matching() -> None:
    result = resolver(
        aliases=(
            CatalogAlias(
                alias="旅行机",
                scope=ObjectScope(store_id=PRIMARY_STORE_ID, product_id="drone-travel"),
            ),
        )
    ).resolve(ExplicitReference(product_name="旅行机"))

    assert result.status is ReferenceResolutionStatus.RESOLVED
    assert result.scope == ObjectScope(
        store_id=PRIMARY_STORE_ID, product_id="drone-travel"
    )


@pytest.mark.parametrize(
    "reference, reason",
    [
        (
            ExplicitReference(product_name="unknown drone"),
            ReferenceClarificationReason.PRODUCT_NOT_FOUND,
        ),
        (
            ExplicitReference(variant_name="unknown combo"),
            ReferenceClarificationReason.VARIANT_NOT_FOUND,
        ),
        (
            ExplicitReference(product_name="Northwind Travel", variant_name="Pro Kit"),
            ReferenceClarificationReason.VARIANT_NOT_OWNED_BY_PRODUCT,
        ),
        (ExplicitReference(), ReferenceClarificationReason.EMPTY_REFERENCE),
    ],
)
def test_zero_and_wrong_parent_matches_fail_closed(reference, reason) -> None:
    result = resolver().resolve(reference)

    assert result.status is ReferenceResolutionStatus.NEEDS_CLARIFICATION
    assert result.scope is None
    assert result.clarification_reason is reason


def test_multiple_controlled_alias_matches_never_choose_the_first_candidate() -> None:
    aliases = (
        CatalogAlias(
            alias="旗舰机",
            scope=ObjectScope(store_id=PRIMARY_STORE_ID, product_id="drone-travel"),
        ),
        CatalogAlias(
            alias="旗舰机",
            scope=ObjectScope(store_id=PRIMARY_STORE_ID, product_id="drone-cinema"),
        ),
    )

    result = resolver(aliases=aliases).resolve(ExplicitReference(product_name="旗舰机"))

    assert result.status is ReferenceResolutionStatus.NEEDS_CLARIFICATION
    assert result.clarification_reason is ReferenceClarificationReason.PRODUCT_AMBIGUOUS
    assert result.candidates == tuple(alias.scope for alias in aliases)


def test_foreign_store_alias_is_rejected_at_registry_construction() -> None:
    with pytest.raises(ValueError, match="store boundary"):
        resolver(
            aliases=(
                CatalogAlias(
                    alias="旅行机",
                    scope=ObjectScope(
                        store_id=ISOLATION_STORE_ID, product_id="drone-travel"
                    ),
                ),
            )
        )
