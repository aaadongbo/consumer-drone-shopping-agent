"""S02-T03 Variant-level HARD eligibility tests."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    DeterministicCatalogFixture,
    EligibilityRejectionCode,
    VariantCommerceSnapshot,
    evaluate_variant_eligibility,
)
from backend.catalog.fixture import PRIMARY_STORE_ID, CommerceState
from backend.common import ToolErrorCode, ToolResult, ToolStatus
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperator,
    ConstraintProvenance,
    NormalizedConstraint,
)

pytestmark = pytest.mark.unit

OBSERVED_AT = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)


def load():
    return DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=PRIMARY_STORE_ID
    )


def variant_and_commerce(product_id: str, variant_id: str):
    snapshot = load()
    variant = next(
        item
        for item in snapshot.variants
        if item.product_id == product_id and item.variant_id == variant_id
    )
    commerce = next(
        item
        for item in snapshot.commerce
        if item.product_id == product_id and item.variant_id == variant_id
    )
    return variant, commerce


def hard(
    field: ConstraintField,
    operator: ConstraintOperator,
    value: object,
    unit: str | None,
) -> NormalizedConstraint:
    return NormalizedConstraint(
        source_turn_id="msg-s02-t03",
        field=field,
        operator=operator,
        value=value,
        unit=unit,
        hardness=ConstraintHardness.HARD,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def soft(
    field: ConstraintField,
    operator: ConstraintOperator,
    value: object,
    unit: str | None,
) -> NormalizedConstraint:
    return NormalizedConstraint(
        source_turn_id="msg-s02-t03",
        field=field,
        operator=operator,
        value=value,
        unit=unit,
        hardness=ConstraintHardness.SOFT,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def test_available_variant_that_satisfies_all_hard_constraints_is_eligible() -> None:
    variant, commerce = variant_and_commerce("drone-travel", "travel-lite")

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=commerce,
        constraints=[
            hard(ConstraintField.PRICE, ConstraintOperator.LTE, 3000, "CNY"),
            hard(ConstraintField.TAKEOFF_WEIGHT, ConstraintOperator.LTE, 250, "g"),
            hard(ConstraintField.BATTERY_COUNT, ConstraintOperator.GTE, 1, "battery"),
        ],
    )

    assert result.eligible is True
    assert result.rejection_reasons == ()
    assert [item.satisfied for item in result.evaluated_constraints] == [
        True,
        True,
        True,
    ]
    assert result.observed_at == OBSERVED_AT


def test_current_availability_is_required_even_when_hard_fields_match() -> None:
    variant, commerce = variant_and_commerce("drone-travel", "travel-pack")

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=commerce,
        constraints=[
            hard(ConstraintField.BATTERY_COUNT, ConstraintOperator.GTE, 3, "battery")
        ],
    )

    assert result.eligible is False
    assert EligibilityRejectionCode.VARIANT_UNAVAILABLE in {
        reason.code for reason in result.rejection_reasons
    }
    assert result.evaluated_constraints[0].satisfied is True


def test_unknown_hard_variant_attribute_fails_closed() -> None:
    variant, commerce = variant_and_commerce("drone-survey", "survey-base")

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=commerce,
        constraints=[
            hard(ConstraintField.TAKEOFF_WEIGHT, ConstraintOperator.LTE, 250, "g")
        ],
    )

    assert result.eligible is False
    assert result.evaluated_constraints[0].actual is not None
    assert result.evaluated_constraints[0].rejection_code is (
        EligibilityRejectionCode.HARD_FIELD_UNKNOWN
    )


def test_not_applicable_hard_variant_attribute_fails_closed() -> None:
    variant, commerce = variant_and_commerce("drone-survey", "survey-base")
    constraint = NormalizedConstraint(
        source_turn_id="msg-s02-t03",
        field=ConstraintField.OBSTACLE_SENSING,
        operator=ConstraintOperator.PRESENT,
        value=True,
        unit=None,
        hardness=ConstraintHardness.HARD,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=commerce,
        constraints=[constraint],
    )

    assert result.eligible is False
    assert result.evaluated_constraints[0].rejection_code is (
        EligibilityRejectionCode.HARD_FIELD_NOT_APPLICABLE
    )


def test_price_uses_exact_variant_commerce_not_neighboring_variant() -> None:
    variant, commerce = variant_and_commerce("drone-cinema", "cinema-pro")

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=commerce,
        constraints=[hard(ConstraintField.PRICE, ConstraintOperator.LTE, 5000, "CNY")],
    )

    assert result.eligible is False
    assert result.evaluated_constraints[0].actual is not None
    assert result.evaluated_constraints[0].actual.value == 8999
    assert result.evaluated_constraints[0].rejection_code is (
        EligibilityRejectionCode.HARD_CONSTRAINT_NOT_SATISFIED
    )


def test_soft_constraints_do_not_affect_t03_hard_eligibility() -> None:
    variant, commerce = variant_and_commerce("drone-cinema", "cinema-pro")

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=commerce,
        constraints=[
            soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "travel", None),
            soft(ConstraintField.CAMERA_RESOLUTION, ConstraintOperator.EQ, "4K", None),
        ],
    )

    assert result.eligible is True
    assert result.evaluated_constraints == ()


def test_variant_and_commerce_identity_must_match_exactly() -> None:
    travel, _travel_commerce = variant_and_commerce("drone-travel", "travel-lite")
    _cinema, cinema_commerce = variant_and_commerce("drone-cinema", "cinema-pro")

    with pytest.raises(ValueError, match="identities must match exactly"):
        evaluate_variant_eligibility(
            variant=travel,
            commerce=cinema_commerce,
            constraints=[],
        )


def test_partial_commerce_result_fails_closed_without_using_incomplete_data() -> None:
    variant, commerce = variant_and_commerce("drone-travel", "travel-lite")
    assert commerce.result.data is not None
    partial_commerce = VariantCommerceSnapshot(
        store_id=commerce.store_id,
        product_id=commerce.product_id,
        variant_id=commerce.variant_id,
        result=ToolResult[CommerceState](
            status=ToolStatus.PARTIAL,
            data={
                "price": commerce.result.data["price"],
                "availability": commerce.result.data["availability"],
            },
            source=commerce.result.source,
            observed_at=commerce.result.observed_at,
            retryable=True,
            missing_fields=["inventory"],
        ),
    )

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=partial_commerce,
        constraints=[hard(ConstraintField.PRICE, ConstraintOperator.LTE, 3000, "CNY")],
    )

    assert result.eligible is False
    assert result.rejection_reasons[0].code is (
        EligibilityRejectionCode.COMMERCE_RESULT_PARTIAL
    )
    assert result.evaluated_constraints[0].actual is None
    assert result.evaluated_constraints[0].rejection_code is (
        EligibilityRejectionCode.COMMERCE_RESULT_PARTIAL
    )


def test_error_commerce_result_returns_fail_closed_result_instead_of_raising() -> None:
    variant, commerce = variant_and_commerce("drone-travel", "travel-lite")
    error_commerce = VariantCommerceSnapshot(
        store_id=commerce.store_id,
        product_id=commerce.product_id,
        variant_id=commerce.variant_id,
        result=ToolResult[CommerceState](
            status=ToolStatus.ERROR,
            source=commerce.result.source,
            observed_at=commerce.result.observed_at,
            error_code=ToolErrorCode.TIMEOUT,
            retryable=True,
        ),
    )

    result = evaluate_variant_eligibility(
        variant=variant,
        commerce=error_commerce,
        constraints=[
            hard(ConstraintField.BATTERY_COUNT, ConstraintOperator.GTE, 1, "battery")
        ],
    )

    assert result.eligible is False
    assert result.rejection_reasons[0].code is (
        EligibilityRejectionCode.COMMERCE_RESULT_ERROR
    )
    assert result.evaluated_constraints[0].rejection_code is (
        EligibilityRejectionCode.COMMERCE_RESULT_ERROR
    )
