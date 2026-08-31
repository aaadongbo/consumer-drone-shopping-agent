"""Deterministic Variant-level HARD eligibility for Slice 2."""

from collections.abc import Iterable
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, JsonValue

from backend.catalog.fixture import CatalogFixtureSnapshot, VariantCommerceSnapshot
from backend.common import AttributeStatus, AttributeValue, VariantRecord
from backend.common.contracts import SCHEMA_VERSION, ToolStatus, WireModel
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperator,
    NormalizedConstraint,
)

type SchemaVersion = Literal["1.0"]

_COMMERCE_FIELDS = {
    ConstraintField.PRICE: "price",
}

_VARIANT_FIELDS = {
    ConstraintField.BATTERY_COUNT: "battery_count",
    ConstraintField.TAKEOFF_WEIGHT: "takeoff_weight",
    ConstraintField.OBSTACLE_SENSING: "obstacle_sensing",
}


class EligibilityRejectionCode(StrEnum):
    """Machine-readable reasons a Variant cannot enter recommendation candidates."""

    VARIANT_UNAVAILABLE = "VARIANT_UNAVAILABLE"
    COMMERCE_FIELD_MISSING = "COMMERCE_FIELD_MISSING"
    COMMERCE_FIELD_UNKNOWN = "COMMERCE_FIELD_UNKNOWN"
    COMMERCE_FIELD_NOT_APPLICABLE = "COMMERCE_FIELD_NOT_APPLICABLE"
    COMMERCE_RESULT_PARTIAL = "COMMERCE_RESULT_PARTIAL"
    COMMERCE_RESULT_ERROR = "COMMERCE_RESULT_ERROR"
    HARD_FIELD_MISSING = "HARD_FIELD_MISSING"
    HARD_FIELD_UNKNOWN = "HARD_FIELD_UNKNOWN"
    HARD_FIELD_NOT_APPLICABLE = "HARD_FIELD_NOT_APPLICABLE"
    HARD_CONSTRAINT_NOT_SATISFIED = "HARD_CONSTRAINT_NOT_SATISFIED"
    HARD_FIELD_UNSUPPORTED = "HARD_FIELD_UNSUPPORTED"


class EligibilityRejectionReason(WireModel):
    """One auditable fail-closed reason for a concrete Variant."""

    code: EligibilityRejectionCode
    field: str
    message: str


class EvaluatedConstraint(WireModel):
    """A single HARD constraint evaluation against one exact Variant scope."""

    field: ConstraintField
    operator: ConstraintOperator
    expected_value: JsonValue
    expected_unit: str | None = None
    actual: AttributeValue | None = None
    satisfied: bool
    rejection_code: EligibilityRejectionCode | None = None


class EligibilityResult(WireModel):
    """The minimal Slice 2 eligibility contract."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    store_id: str
    product_id: str
    variant_id: str
    eligible: bool
    rejection_reasons: tuple[EligibilityRejectionReason, ...]
    evaluated_constraints: tuple[EvaluatedConstraint, ...]
    observed_at: AwareDatetime


def evaluate_variant_eligibility(
    *,
    variant: VariantRecord,
    commerce: VariantCommerceSnapshot,
    constraints: Iterable[NormalizedConstraint],
) -> EligibilityResult:
    """Evaluate HARD constraints without ranking, model calls, or cross-Variant data."""
    _ensure_same_identity(variant, commerce)
    rejection_reasons: list[EligibilityRejectionReason] = []
    evaluated_constraints: list[EvaluatedConstraint] = []

    commerce_status_rejection = _commerce_status_rejection(commerce)
    if commerce_status_rejection is not None:
        rejection_reasons.append(commerce_status_rejection)
    else:
        commerce_data = _require_commerce_data(commerce)
        availability_rejection = _availability_rejection(commerce_data)
        if availability_rejection is not None:
            rejection_reasons.append(availability_rejection)

    for constraint in constraints:
        if constraint.hardness is not ConstraintHardness.HARD:
            continue
        if commerce_status_rejection is not None:
            evaluation = _failed_by_commerce_status(
                constraint,
                commerce_status_rejection.code,
            )
        else:
            evaluation = _evaluate_hard_constraint(variant, commerce, constraint)
        evaluated_constraints.append(evaluation)
        if evaluation.rejection_code is not None:
            rejection_reasons.append(
                EligibilityRejectionReason(
                    code=evaluation.rejection_code,
                    field=constraint.field.value,
                    message=_message_for(evaluation.rejection_code, constraint.field),
                )
            )

    return EligibilityResult(
        store_id=variant.store_id,
        product_id=variant.product_id,
        variant_id=variant.variant_id,
        eligible=not rejection_reasons,
        rejection_reasons=tuple(rejection_reasons),
        evaluated_constraints=tuple(evaluated_constraints),
        observed_at=commerce.result.observed_at,
    )


def evaluate_store_eligibility(
    *,
    snapshot: CatalogFixtureSnapshot,
    constraints: Iterable[NormalizedConstraint],
) -> tuple[EligibilityResult, ...]:
    """Evaluate every Variant in a store snapshot with exact commerce ownership."""
    constraints_tuple = tuple(constraints)
    commerce_by_identity = {
        (entry.store_id, entry.product_id, entry.variant_id): entry
        for entry in snapshot.commerce
    }
    return tuple(
        evaluate_variant_eligibility(
            variant=variant,
            commerce=commerce_by_identity[
                (variant.store_id, variant.product_id, variant.variant_id)
            ],
            constraints=constraints_tuple,
        )
        for variant in snapshot.variants
    )


def _ensure_same_identity(
    variant: VariantRecord, commerce: VariantCommerceSnapshot
) -> None:
    variant_identity = (variant.store_id, variant.product_id, variant.variant_id)
    commerce_identity = (commerce.store_id, commerce.product_id, commerce.variant_id)
    if variant_identity != commerce_identity:
        raise ValueError("Variant and commerce snapshot identities must match exactly")


def _require_commerce_data(
    commerce: VariantCommerceSnapshot,
) -> dict[str, AttributeValue]:
    if commerce.result.data is None:
        raise ValueError("Eligibility requires typed commerce data")
    return commerce.result.data


def _commerce_status_rejection(
    commerce: VariantCommerceSnapshot,
) -> EligibilityRejectionReason | None:
    if commerce.result.status is ToolStatus.SUCCESS:
        return None
    if commerce.result.status is ToolStatus.PARTIAL:
        return EligibilityRejectionReason(
            code=EligibilityRejectionCode.COMMERCE_RESULT_PARTIAL,
            field="commerce",
            message="Current commerce result is partial.",
        )
    return EligibilityRejectionReason(
        code=EligibilityRejectionCode.COMMERCE_RESULT_ERROR,
        field="commerce",
        message="Current commerce result is unavailable.",
    )


def _availability_rejection(
    commerce_data: dict[str, AttributeValue],
) -> EligibilityRejectionReason | None:
    availability = commerce_data.get("availability")
    if availability is None:
        return EligibilityRejectionReason(
            code=EligibilityRejectionCode.COMMERCE_FIELD_MISSING,
            field="availability",
            message="Current availability is missing.",
        )
    if availability.status is AttributeStatus.UNKNOWN:
        return EligibilityRejectionReason(
            code=EligibilityRejectionCode.COMMERCE_FIELD_UNKNOWN,
            field="availability",
            message="Current availability is unknown.",
        )
    if availability.status is AttributeStatus.NOT_APPLICABLE:
        return EligibilityRejectionReason(
            code=EligibilityRejectionCode.COMMERCE_FIELD_NOT_APPLICABLE,
            field="availability",
            message="Current availability is not applicable.",
        )
    if availability.value is not True:
        return EligibilityRejectionReason(
            code=EligibilityRejectionCode.VARIANT_UNAVAILABLE,
            field="availability",
            message="Variant is not currently available.",
        )
    return None


def _evaluate_hard_constraint(
    variant: VariantRecord,
    commerce: VariantCommerceSnapshot,
    constraint: NormalizedConstraint,
) -> EvaluatedConstraint:
    fact = _fact_for_constraint(variant, commerce, constraint.field)
    rejection_code = _fact_rejection_code(constraint.field, fact)
    if rejection_code is not None:
        return EvaluatedConstraint(
            field=constraint.field,
            operator=constraint.operator,
            expected_value=constraint.value,
            expected_unit=constraint.unit,
            actual=fact,
            satisfied=False,
            rejection_code=rejection_code,
        )

    assert fact is not None
    satisfied = _compare(fact.value, constraint.operator, constraint.value)
    return EvaluatedConstraint(
        field=constraint.field,
        operator=constraint.operator,
        expected_value=constraint.value,
        expected_unit=constraint.unit,
        actual=fact,
        satisfied=satisfied,
        rejection_code=None
        if satisfied
        else EligibilityRejectionCode.HARD_CONSTRAINT_NOT_SATISFIED,
    )


def _failed_by_commerce_status(
    constraint: NormalizedConstraint,
    code: EligibilityRejectionCode,
) -> EvaluatedConstraint:
    return EvaluatedConstraint(
        field=constraint.field,
        operator=constraint.operator,
        expected_value=constraint.value,
        expected_unit=constraint.unit,
        actual=None,
        satisfied=False,
        rejection_code=code,
    )


def _fact_for_constraint(
    variant: VariantRecord,
    commerce: VariantCommerceSnapshot,
    field: ConstraintField,
) -> AttributeValue | None:
    if field in _COMMERCE_FIELDS:
        return _require_commerce_data(commerce).get(_COMMERCE_FIELDS[field])
    if field in _VARIANT_FIELDS:
        return variant.variant_attributes.get(_VARIANT_FIELDS[field])
    return None


def _fact_rejection_code(
    field: ConstraintField,
    fact: AttributeValue | None,
) -> EligibilityRejectionCode | None:
    if fact is None:
        if field in _COMMERCE_FIELDS:
            return EligibilityRejectionCode.COMMERCE_FIELD_MISSING
        if field in _VARIANT_FIELDS:
            return EligibilityRejectionCode.HARD_FIELD_MISSING
        return EligibilityRejectionCode.HARD_FIELD_UNSUPPORTED
    if fact.status is AttributeStatus.UNKNOWN:
        if field in _COMMERCE_FIELDS:
            return EligibilityRejectionCode.COMMERCE_FIELD_UNKNOWN
        return EligibilityRejectionCode.HARD_FIELD_UNKNOWN
    if fact.status is AttributeStatus.NOT_APPLICABLE:
        if field in _COMMERCE_FIELDS:
            return EligibilityRejectionCode.COMMERCE_FIELD_NOT_APPLICABLE
        return EligibilityRejectionCode.HARD_FIELD_NOT_APPLICABLE
    return None


def _compare(
    actual: JsonValue | None,
    operator: ConstraintOperator,
    expected: JsonValue,
) -> bool:
    if operator is ConstraintOperator.LTE:
        return _as_number(actual) <= _as_number(expected)
    if operator is ConstraintOperator.GTE:
        return _as_number(actual) >= _as_number(expected)
    if operator is ConstraintOperator.EQ:
        return actual == expected
    if operator is ConstraintOperator.PRESENT:
        return actual not in (None, False, "")
    raise ValueError(f"Unsupported constraint operator: {operator}")


def _as_number(value: JsonValue | None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Numeric eligibility comparisons require numeric values")
    return float(value)


def _message_for(
    code: EligibilityRejectionCode,
    field: ConstraintField,
) -> str:
    if code is EligibilityRejectionCode.HARD_CONSTRAINT_NOT_SATISFIED:
        return f"{field.value} does not satisfy the HARD constraint."
    if code is EligibilityRejectionCode.HARD_FIELD_UNSUPPORTED:
        return f"{field.value} is not supported by HARD eligibility."
    if code is EligibilityRejectionCode.COMMERCE_RESULT_PARTIAL:
        return "Current commerce result is partial."
    if code is EligibilityRejectionCode.COMMERCE_RESULT_ERROR:
        return "Current commerce result is unavailable."
    if code in {
        EligibilityRejectionCode.HARD_FIELD_UNKNOWN,
        EligibilityRejectionCode.COMMERCE_FIELD_UNKNOWN,
    }:
        return f"{field.value} is unknown."
    if code in {
        EligibilityRejectionCode.HARD_FIELD_NOT_APPLICABLE,
        EligibilityRejectionCode.COMMERCE_FIELD_NOT_APPLICABLE,
    }:
        return f"{field.value} is not applicable."
    return f"{field.value} is missing."
