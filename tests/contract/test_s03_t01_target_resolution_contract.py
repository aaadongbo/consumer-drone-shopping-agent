"""S03-T01 contract and golden-matrix tests for target-resolution proposals."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.common import ObjectScope
from backend.conversation.target_resolution import (
    ComparisonMember,
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)

pytestmark = pytest.mark.contract

_GOLDEN_MATRIX = (
    Path(__file__).parents[1] / "fixtures" / "s03_t01_target_resolution_golden.json"
)


def scope(product_id: str, variant_id: str | None = None) -> ObjectScope:
    return ObjectScope(
        store_id="store-s02-alpha",
        product_id=product_id,
        variant_id=variant_id,
    )


def single_target(product_id: str = "drone-travel") -> TurnTarget:
    return TurnTarget(kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope(product_id))


def test_golden_matrix_is_serializable_and_validated() -> None:
    rows = json.loads(_GOLDEN_MATRIX.read_text(encoding="utf-8"))

    resolutions = [TargetResolution.model_validate(row["expected"]) for row in rows]

    assert [row["case_id"] for row in rows] == [
        "page-default-single-object",
        "explicit-temporary-other-product",
        "confirmed-switch-single-object",
        "comparison-per-member-provenance",
        "unresolved-reference-clarification",
        "recommendation-is-not-page-scoped",
        "store-support-is-not-product-qa",
    ]
    assert [resolution.turn_target.kind for resolution in resolutions] == [
        TurnTargetKind.SINGLE_OBJECT,
        TurnTargetKind.SINGLE_OBJECT,
        TurnTargetKind.SINGLE_OBJECT,
        TurnTargetKind.COMPARISON_SET,
        TurnTargetKind.NEEDS_CLARIFICATION,
        TurnTargetKind.RECOMMENDATION_TASK,
        TurnTargetKind.STORE_SUPPORT,
    ]
    assert all(
        TargetResolution.model_validate_json(resolution.to_wire_json()) == resolution
        for resolution in resolutions
    )


@pytest.mark.parametrize(
    "kind",
    [
        TurnTargetKind.SINGLE_OBJECT,
        TurnTargetKind.COMPARISON_SET,
        TurnTargetKind.RECOMMENDATION_TASK,
        TurnTargetKind.STORE_SUPPORT,
        TurnTargetKind.NEEDS_CLARIFICATION,
    ],
)
def test_all_turn_target_kinds_have_a_valid_minimal_shape(kind: TurnTargetKind) -> None:
    if kind is TurnTargetKind.SINGLE_OBJECT:
        target = single_target()
    elif kind is TurnTargetKind.COMPARISON_SET:
        target = TurnTarget(
            kind=kind,
            comparison_members=(
                ComparisonMember(
                    scope=scope("drone-travel"), provenance="PAGE_CONTEXT"
                ),
                ComparisonMember(scope=scope("drone-cinema"), provenance="EXPLICIT"),
            ),
        )
    elif kind is TurnTargetKind.NEEDS_CLARIFICATION:
        target = TurnTarget(kind=kind, clarification_reason="PRODUCT_AMBIGUOUS")
    else:
        target = TurnTarget(kind=kind)

    assert target.kind is kind


@pytest.mark.parametrize(
    "target",
    [
        TurnTarget(kind=TurnTargetKind.RECOMMENDATION_TASK),
        TurnTarget(kind=TurnTargetKind.STORE_SUPPORT),
        TurnTarget(
            kind=TurnTargetKind.NEEDS_CLARIFICATION,
            clarification_reason="PRODUCT_AMBIGUOUS",
        ),
    ],
)
def test_only_single_object_can_carry_a_single_resolution_source(
    target: TurnTarget,
) -> None:
    with pytest.raises(ValidationError):
        TargetResolution(
            turn_target=target,
            resolution_source=ResolutionSource.UNRESOLVED,
            context_action=ContextAction.KEEP,
        )


def test_single_object_requires_one_resolved_source() -> None:
    with pytest.raises(ValidationError):
        TargetResolution(turn_target=single_target(), context_action=ContextAction.KEEP)
    with pytest.raises(ValidationError):
        TargetResolution(
            turn_target=single_target(),
            resolution_source=ResolutionSource.UNRESOLVED,
            context_action=ContextAction.KEEP,
        )


def test_comparison_uses_per_member_provenance_and_unique_two_to_four_members() -> None:
    comparison = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            ComparisonMember(
                scope=scope("drone-travel"),
                provenance=ResolutionSource.CONFIRMED_CONTEXT,
            ),
            ComparisonMember(
                scope=scope("drone-cinema"), provenance=ResolutionSource.EXPLICIT
            ),
        ),
    )

    assert (
        comparison.comparison_members[0].provenance
        is ResolutionSource.CONFIRMED_CONTEXT
    )
    with pytest.raises(ValidationError):
        ComparisonMember(
            scope=scope("drone-travel"), provenance=ResolutionSource.UNRESOLVED
        )
    with pytest.raises(ValidationError):
        TurnTarget(
            kind=TurnTargetKind.COMPARISON_SET,
            comparison_members=(
                ComparisonMember(
                    scope=scope("drone-travel"),
                    provenance=ResolutionSource.PAGE_CONTEXT,
                ),
            ),
        )


@pytest.mark.parametrize(
    "action", [ContextAction.AWAIT_CONFIRMATION, ContextAction.SWITCH_CONFIRMED]
)
def test_context_switch_actions_require_one_single_object(
    action: ContextAction,
) -> None:
    with pytest.raises(ValidationError):
        TargetResolution(
            turn_target=TurnTarget(kind=TurnTargetKind.STORE_SUPPORT),
            context_action=action,
        )


def test_target_contract_is_internal_and_does_not_expand_turn_request_wire_schema() -> (
    None
):
    from backend.common import TurnRequest

    turn_schema = TurnRequest.model_json_schema()
    page_context_schema = turn_schema["$defs"]["PageContext"]

    assert "expected_revision" not in json.dumps(turn_schema)
    assert "bundle" not in json.dumps(turn_schema)
    assert "store_id" in turn_schema["properties"]
    assert set(page_context_schema["properties"]) == {"product_id", "variant_id"}
