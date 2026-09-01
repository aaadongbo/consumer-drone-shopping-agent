"""S03-T03 store-isolation and ownership integration coverage."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    CatalogReferenceResolver,
    DeterministicCatalogFixture,
    ExplicitReference,
    ReferenceClarificationReason,
    ReferenceResolutionStatus,
)
from backend.catalog.fixture import ISOLATION_STORE_ID, PRIMARY_STORE_ID

pytestmark = pytest.mark.integration


def test_identical_product_surface_is_resolved_only_inside_requested_store() -> None:
    fixture = DeterministicCatalogFixture(
        observed_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    )
    primary = CatalogReferenceResolver(
        snapshot=fixture.load_store(store_id=PRIMARY_STORE_ID)
    )
    isolated = CatalogReferenceResolver(
        snapshot=fixture.load_store(store_id=ISOLATION_STORE_ID)
    )

    primary_result = primary.resolve(ExplicitReference(product_name="drone-travel"))
    isolated_result = isolated.resolve(ExplicitReference(product_name="drone-travel"))

    assert primary_result.scope is not None
    assert isolated_result.scope is not None
    assert primary_result.scope.store_id == PRIMARY_STORE_ID
    assert isolated_result.scope.store_id == ISOLATION_STORE_ID


def test_foreign_variant_is_not_accepted_as_an_owned_variant() -> None:
    fixture = DeterministicCatalogFixture(
        observed_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    )
    isolated = CatalogReferenceResolver(
        snapshot=fixture.load_store(store_id=ISOLATION_STORE_ID)
    )

    result = isolated.resolve(ExplicitReference(variant_name="Lite Combo"))

    assert result.status is ReferenceResolutionStatus.NEEDS_CLARIFICATION
    assert result.clarification_reason is ReferenceClarificationReason.VARIANT_NOT_FOUND
