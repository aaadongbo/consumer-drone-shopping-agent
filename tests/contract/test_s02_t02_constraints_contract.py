"""S02-T02 contract tests for single-turn constraint patches."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.common import SCHEMA_VERSION, ConversationRef, PageContext, TurnRequest
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperation,
    ConstraintOperator,
    ConstraintPatch,
    ConstraintProvenance,
    NormalizedConstraint,
    normalize_constraint_patch,
)

pytestmark = pytest.mark.contract


def turn(text: str = "预算 5000 元以内") -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-s02-alpha",
        conversation=ConversationRef(
            conversation_id="conv-s02", message_id="msg-s02-t02"
        ),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )


def patch(**overrides: object) -> ConstraintPatch:
    data = {
        "source_turn_id": turn().conversation.message_id,
        "operation": ConstraintOperation.ADD,
        "field": ConstraintField.PRICE,
        "operator": ConstraintOperator.LTE,
        "value": 5000,
        "unit": "CNY",
        "hardness": ConstraintHardness.HARD,
        "confidence": 1.0,
        "provenance": ConstraintProvenance.DETERMINISTIC_RULE,
        "reason": "test",
    }
    data.update(overrides)
    return ConstraintPatch(**data)


def test_constraint_patch_round_trips_wire_json() -> None:
    original = patch()

    restored = ConstraintPatch.model_validate_json(original.to_wire_json())

    assert restored == original
    assert restored.schema_version == SCHEMA_VERSION
    assert restored.source_turn_id == "msg-s02-t02"


def test_normalized_constraint_round_trips_wire_json() -> None:
    normalized = normalize_constraint_patch(
        patch(field=ConstraintField.TAKEOFF_WEIGHT, value=0.25, unit="kg")
    )

    assert normalized is not None
    restored = NormalizedConstraint.model_validate_json(normalized.to_wire_json())

    assert restored == normalized
    assert restored.value == 250
    assert restored.unit == "g"


def test_no_change_must_omit_constraint_semantics() -> None:
    no_change = ConstraintPatch(
        source_turn_id="msg-unsupported",
        operation=ConstraintOperation.NO_CHANGE,
        confidence=0.0,
        provenance=ConstraintProvenance.UNSUPPORTED_INPUT,
        reason="unsupported",
    )

    assert no_change.to_wire() == {
        "schema_version": SCHEMA_VERSION,
        "source_turn_id": "msg-unsupported",
        "operation": "NO_CHANGE",
        "confidence": 0.0,
        "provenance": "UNSUPPORTED_INPUT",
        "reason": "unsupported",
    }
    with pytest.raises(ValidationError):
        ConstraintPatch(
            source_turn_id="msg-unsupported",
            operation=ConstraintOperation.NO_CHANGE,
            field=ConstraintField.PRICE,
            confidence=0.0,
            provenance=ConstraintProvenance.UNSUPPORTED_INPUT,
            reason="unsupported",
        )


@pytest.mark.parametrize(
    ("field", "unit"),
    [
        (ConstraintField.PRICE, "USD"),
        (ConstraintField.TAKEOFF_WEIGHT, "lb"),
        (ConstraintField.BATTERY_COUNT, "unit"),
        (ConstraintField.USE_CASE, "CNY"),
    ],
)
def test_invalid_units_are_rejected(field: ConstraintField, unit: str) -> None:
    with pytest.raises(ValidationError):
        patch(field=field, unit=unit)


def test_numeric_fields_reject_text_values() -> None:
    with pytest.raises(ValidationError):
        patch(field=ConstraintField.PRICE, value="cheap")


def test_numeric_fields_reject_bool_values() -> None:
    with pytest.raises(ValidationError):
        patch(field=ConstraintField.PRICE, value=True)


def test_non_numeric_fields_reject_numeric_values() -> None:
    with pytest.raises(ValidationError):
        patch(
            field=ConstraintField.USE_CASE,
            operator=ConstraintOperator.EQ,
            value=123,
            unit=None,
            hardness=ConstraintHardness.SOFT,
        )


def test_present_operator_is_not_valid_for_numeric_fields() -> None:
    with pytest.raises(ValidationError):
        patch(operator=ConstraintOperator.PRESENT)


def test_order_must_match_field_semantics() -> None:
    with pytest.raises(ValidationError):
        patch(
            field=ConstraintField.USE_CASE,
            operator=ConstraintOperator.LTE,
            value="travel",
            unit=None,
            hardness=ConstraintHardness.SOFT,
        )


def test_normalized_constraint_rejects_non_canonical_unit() -> None:
    with pytest.raises(ValidationError):
        NormalizedConstraint(
            source_turn_id="msg",
            field=ConstraintField.TAKEOFF_WEIGHT,
            operator=ConstraintOperator.LTE,
            value=250,
            unit="kg",
            hardness=ConstraintHardness.HARD,
            confidence=1.0,
            provenance=ConstraintProvenance.DETERMINISTIC_RULE,
        )


def test_naive_datetime_import_is_not_part_of_t02_contract() -> None:
    assert datetime(2026, 8, 31, tzinfo=UTC).tzinfo is not None
