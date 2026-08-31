"""S02-T02 deterministic parser and normalization tests."""

import pytest

from backend.common import SCHEMA_VERSION, ConversationRef, PageContext, TurnRequest
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperation,
    ConstraintOperator,
    ConstraintProvenance,
    normalize_constraint_patches,
    parse_constraint_patches,
)

pytestmark = pytest.mark.unit


def turn(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-s02-alpha",
        conversation=ConversationRef(conversation_id="conv-s02", message_id="msg-001"),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )


def only_patch(text: str):
    patches = parse_constraint_patches(turn(text))
    assert len(patches) == 1
    return patches[0]


def test_budget_ceiling_parses_as_hard_price_constraint() -> None:
    patch = only_patch("预算 5000 元以内，适合入门")
    normalized = normalize_constraint_patches((patch,))

    assert patch.operation is ConstraintOperation.ADD
    assert patch.field is ConstraintField.PRICE
    assert patch.operator is ConstraintOperator.LTE
    assert patch.value == 5000
    assert patch.unit == "CNY"
    assert patch.hardness is ConstraintHardness.HARD
    assert normalized[0].value == 5000
    assert normalized[0].unit == "CNY"


def test_takeoff_weight_normalizes_kg_to_grams() -> None:
    patch = only_patch("想要起飞重量 0.25kg 以下的")
    normalized = normalize_constraint_patches((patch,))

    assert patch.field is ConstraintField.TAKEOFF_WEIGHT
    assert patch.value == 0.25
    assert patch.unit == "kg"
    assert patch.hardness is ConstraintHardness.HARD
    assert normalized[0].value == 250
    assert normalized[0].unit == "g"


def test_takeoff_weight_accepts_gram_wording() -> None:
    patch = only_patch("最好起飞重量250克以内")
    normalized = normalize_constraint_patches((patch,))

    assert patch.field is ConstraintField.TAKEOFF_WEIGHT
    assert patch.value == 250
    assert normalized[0].value == 250


def test_minimum_battery_count_parses_as_hard_constraint() -> None:
    patch = only_patch("至少 2 块电池")
    normalized = normalize_constraint_patches((patch,))

    assert patch.field is ConstraintField.BATTERY_COUNT
    assert patch.operator is ConstraintOperator.GTE
    assert patch.value == 2
    assert patch.unit == "battery"
    assert patch.hardness is ConstraintHardness.HARD
    assert normalized[0].value == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("适合旅行的无人机", "travel"),
        ("用于电影拍片", "cinema"),
        ("巡检测绘使用", "inspection"),
    ],
)
def test_use_case_preferences_are_soft_signals(text: str, expected: str) -> None:
    patch = only_patch(text)

    assert patch.field is ConstraintField.USE_CASE
    assert patch.operator is ConstraintOperator.EQ
    assert patch.value == expected
    assert patch.unit is None
    assert patch.hardness is ConstraintHardness.SOFT


def test_camera_resolution_is_soft_and_deterministic() -> None:
    patch = only_patch("希望能拍 4K")

    assert patch.field is ConstraintField.CAMERA_RESOLUTION
    assert patch.value == "4K"
    assert patch.hardness is ConstraintHardness.SOFT


def test_obstacle_sensing_is_soft_present_signal() -> None:
    patch = only_patch("要有避障更好")

    assert patch.field is ConstraintField.OBSTACLE_SENSING
    assert patch.operator is ConstraintOperator.PRESENT
    assert patch.value is True
    assert patch.hardness is ConstraintHardness.SOFT


def test_multiple_constraints_preserve_turn_source_and_order() -> None:
    patches = parse_constraint_patches(
        turn("预算5000元以内，250g以下，至少2块电池，适合旅行")
    )

    assert [patch.field for patch in patches] == [
        ConstraintField.PRICE,
        ConstraintField.TAKEOFF_WEIGHT,
        ConstraintField.BATTERY_COUNT,
        ConstraintField.USE_CASE,
    ]
    assert {patch.source_turn_id for patch in patches} == {"msg-001"}
    normalized = normalize_constraint_patches(patches)
    assert [item.field for item in normalized] == [patch.field for patch in patches]


def test_unsupported_input_returns_safe_no_change() -> None:
    patch = only_patch("帮我推荐一个酷一点的")

    assert patch.operation is ConstraintOperation.NO_CHANGE
    assert patch.provenance is ConstraintProvenance.UNSUPPORTED_INPUT
    assert patch.confidence == 0.0
    assert normalize_constraint_patches((patch,)) == ()


@pytest.mark.parametrize("text", ["预算 5000 USD以内", "预算 5000美元以内"])
def test_invalid_budget_currency_does_not_guess_cny(text: str) -> None:
    patch = only_patch(text)

    assert patch.operation is ConstraintOperation.NO_CHANGE
    assert patch.provenance is ConstraintProvenance.UNSUPPORTED_INPUT
    assert normalize_constraint_patches((patch,)) == ()


def test_no_multiturn_state_or_revision_is_emitted() -> None:
    patch = only_patch("预算 5000 元以内")
    wire = patch.to_wire()

    assert "state_revision" not in wire
    assert "conversation_state" not in wire
    assert "previous_constraints" not in wire
