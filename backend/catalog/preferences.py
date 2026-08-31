"""Deterministic SOFT preference signals for Slice 2."""

from collections.abc import Iterable
from typing import Literal

from pydantic import JsonValue

from backend.catalog.eligibility import EligibilityResult
from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import AttributeStatus, AttributeValue, ProductRecord, VariantRecord
from backend.common.contracts import SCHEMA_VERSION, WireModel
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperator,
    NormalizedConstraint,
)

type SchemaVersion = Literal["1.0"]

_PRODUCT_SOFT_FIELDS = {
    ConstraintField.USE_CASE: "use_case",
    ConstraintField.CAMERA_RESOLUTION: "camera_resolution",
}

_VARIANT_SOFT_FIELDS = {
    ConstraintField.OBSTACLE_SENSING: "obstacle_sensing",
}


class SoftPreferenceSignal(WireModel):
    """Transparent result of one SOFT preference against one Variant candidate."""

    field: ConstraintField
    operator: ConstraintOperator
    expected_value: JsonValue
    actual: AttributeValue | None = None
    matched: bool
    reason: str


class SoftPreferenceScore(WireModel):
    """Stable, local ranking signal for an already eligible Variant."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    store_id: str
    product_id: str
    variant_id: str
    matched_soft_count: int
    total_soft_count: int
    signals: tuple[SoftPreferenceSignal, ...]
    tie_break_key: tuple[str, str, str]


def score_soft_preferences(
    *,
    product: ProductRecord,
    variant: VariantRecord,
    eligibility: EligibilityResult,
    constraints: Iterable[NormalizedConstraint],
) -> SoftPreferenceScore | None:
    """Score SOFT preferences without changing HARD eligibility."""
    _ensure_same_identity(product, variant, eligibility)
    if not eligibility.eligible:
        return None

    signals = tuple(
        _evaluate_soft_constraint(product, variant, constraint)
        for constraint in constraints
        if constraint.hardness is ConstraintHardness.SOFT
    )
    return SoftPreferenceScore(
        store_id=variant.store_id,
        product_id=variant.product_id,
        variant_id=variant.variant_id,
        matched_soft_count=sum(1 for signal in signals if signal.matched),
        total_soft_count=len(signals),
        signals=signals,
        tie_break_key=(variant.product_id, variant.variant_id, variant.store_id),
    )


def rank_eligible_variants_by_soft_preferences(
    *,
    snapshot: CatalogFixtureSnapshot,
    eligibility_results: Iterable[EligibilityResult],
    constraints: Iterable[NormalizedConstraint],
) -> tuple[SoftPreferenceScore, ...]:
    """Return eligible Variants ordered by SOFT matches and deterministic tie-breaks."""
    constraints_tuple = tuple(constraints)
    products = {product.product_id: product for product in snapshot.products}
    variants = {
        (variant.product_id, variant.variant_id): variant
        for variant in snapshot.variants
    }

    scores = []
    for eligibility in eligibility_results:
        if not eligibility.eligible:
            continue
        variant = variants[(eligibility.product_id, eligibility.variant_id)]
        product = products[eligibility.product_id]
        score = score_soft_preferences(
            product=product,
            variant=variant,
            eligibility=eligibility,
            constraints=constraints_tuple,
        )
        if score is not None:
            scores.append(score)
    return tuple(
        sorted(
            scores,
            key=lambda score: (
                -score.matched_soft_count,
                score.total_soft_count - score.matched_soft_count,
                score.tie_break_key,
            ),
        )
    )


def _ensure_same_identity(
    product: ProductRecord,
    variant: VariantRecord,
    eligibility: EligibilityResult,
) -> None:
    if product.store_id != variant.store_id or product.product_id != variant.product_id:
        raise ValueError("Product and Variant identities must match")
    expected = (variant.store_id, variant.product_id, variant.variant_id)
    actual = (eligibility.store_id, eligibility.product_id, eligibility.variant_id)
    if expected != actual:
        raise ValueError("Eligibility and Variant identities must match")


def _evaluate_soft_constraint(
    product: ProductRecord,
    variant: VariantRecord,
    constraint: NormalizedConstraint,
) -> SoftPreferenceSignal:
    fact = _fact_for_soft_constraint(product, variant, constraint.field)
    matched = _matches(fact, constraint.operator, constraint.value)
    return SoftPreferenceSignal(
        field=constraint.field,
        operator=constraint.operator,
        expected_value=constraint.value,
        actual=fact,
        matched=matched,
        reason=_reason_for(fact, matched),
    )


def _fact_for_soft_constraint(
    product: ProductRecord,
    variant: VariantRecord,
    field: ConstraintField,
) -> AttributeValue | None:
    if field in _PRODUCT_SOFT_FIELDS:
        return product.shared_attributes.get(_PRODUCT_SOFT_FIELDS[field])
    if field in _VARIANT_SOFT_FIELDS:
        return variant.variant_attributes.get(_VARIANT_SOFT_FIELDS[field])
    return None


def _matches(
    fact: AttributeValue | None,
    operator: ConstraintOperator,
    expected: JsonValue,
) -> bool:
    if fact is None or fact.status is not AttributeStatus.KNOWN:
        return False
    if operator is ConstraintOperator.EQ:
        return fact.value == expected
    if operator is ConstraintOperator.PRESENT:
        return fact.value not in (None, False, "")
    return False


def _reason_for(fact: AttributeValue | None, matched: bool) -> str:
    if fact is None:
        return "Soft preference field is missing."
    if fact.status is AttributeStatus.UNKNOWN:
        return "Soft preference field is unknown."
    if fact.status is AttributeStatus.NOT_APPLICABLE:
        return "Soft preference field is not applicable."
    if matched:
        return "Soft preference matched."
    return "Soft preference did not match."
