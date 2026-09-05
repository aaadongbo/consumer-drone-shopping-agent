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
from backend.catalog.pilot_readiness import (
    PILOT_PRODUCT_COUNT,
    PilotDataReadinessReport,
    PilotLaneReport,
    PilotLaneStatus,
    PilotProductIdentity,
    PilotReadinessStopReason,
    PilotVariantIdentity,
    build_pilot_data_readiness_report,
)
from backend.catalog.preferences import (
    SoftPreferenceScore,
    SoftPreferenceSignal,
    rank_eligible_variants_by_soft_preferences,
    score_soft_preferences,
)
from backend.catalog.target_references import (
    CatalogAlias,
    CatalogReferenceResolver,
    ExplicitReference,
    ExplicitReferenceResolution,
    ReferenceClarificationReason,
    ReferenceResolutionStatus,
)

__all__ = [
    "CatalogFixtureSnapshot",
    "DeterministicCatalogFixture",
    "EligibilityRejectionCode",
    "EligibilityRejectionReason",
    "EligibilityResult",
    "EvaluatedConstraint",
    "SoftPreferenceScore",
    "SoftPreferenceSignal",
    "VariantCommerceSnapshot",
    "CatalogAlias",
    "CatalogReferenceResolver",
    "ExplicitReference",
    "ExplicitReferenceResolution",
    "ReferenceClarificationReason",
    "ReferenceResolutionStatus",
    "PILOT_PRODUCT_COUNT",
    "PilotDataReadinessReport",
    "PilotLaneReport",
    "PilotLaneStatus",
    "PilotProductIdentity",
    "PilotReadinessStopReason",
    "PilotVariantIdentity",
    "evaluate_store_eligibility",
    "evaluate_variant_eligibility",
    "rank_eligible_variants_by_soft_preferences",
    "score_soft_preferences",
    "build_pilot_data_readiness_report",
]
