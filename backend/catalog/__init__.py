"""Normalized catalog fixtures for deterministic recommendation work."""

from backend.catalog.eligibility import (
    EligibilityRejectionCode,
    EligibilityRejectionReason,
    EligibilityResult,
    EvaluatedConstraint,
    evaluate_store_eligibility,
    evaluate_variant_eligibility,
)
from backend.catalog.fixture import (
    CatalogFixtureSnapshot,
    DeterministicCatalogFixture,
    VariantCommerceSnapshot,
)

__all__ = [
    "CatalogFixtureSnapshot",
    "DeterministicCatalogFixture",
    "EligibilityRejectionCode",
    "EligibilityRejectionReason",
    "EligibilityResult",
    "EvaluatedConstraint",
    "VariantCommerceSnapshot",
    "evaluate_store_eligibility",
    "evaluate_variant_eligibility",
]
