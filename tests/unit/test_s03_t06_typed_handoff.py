"""S03-T06 typed routing boundaries stay outside Product Fact execution."""

import pytest

from backend.common import ObjectScope
from backend.conversation import (
    ComparisonMember,
    HandoffRoute,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
    TypedHandoffRouter,
)

pytestmark = pytest.mark.unit


def scope(product_id: str) -> ObjectScope:
    return ObjectScope(store_id="store-s03-alpha", product_id=product_id)


def test_comparison_handoff_preserves_each_members_provenance() -> None:
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            ComparisonMember(
                scope=scope("drone-mini"), provenance=ResolutionSource.CONFIRMED_CONTEXT
            ),
            ComparisonMember(
                scope=scope("drone-cinema"), provenance=ResolutionSource.EXPLICIT
            ),
        ),
    )

    handoff = TypedHandoffRouter().route(
        TargetResolution(turn_target=target, context_action="KEEP")
    )

    assert handoff.route is HandoffRoute.COMPARISON
    assert [member.provenance for member in handoff.target.comparison_members] == [
        ResolutionSource.CONFIRMED_CONTEXT,
        ResolutionSource.EXPLICIT,
    ]
    assert handoff.downstream_execution_allowed is False


@pytest.mark.parametrize(
    ("kind", "route"),
    [
        (TurnTargetKind.RECOMMENDATION_TASK, HandoffRoute.RECOMMENDATION),
        (TurnTargetKind.STORE_SUPPORT, HandoffRoute.STORE_SUPPORT),
    ],
)
def test_recommendation_and_support_are_typed_handoffs(
    kind: TurnTargetKind, route: HandoffRoute
) -> None:
    handoff = TypedHandoffRouter().route(
        TargetResolution(
            turn_target=TurnTarget(kind=kind),
            context_action="KEEP",
        )
    )

    assert handoff.route is route
    assert handoff.target.object_scope is None
    assert handoff.downstream_execution_allowed is False


def test_clarification_is_a_typed_boundary_not_a_product_fact_fallback() -> None:
    resolution = TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.NEEDS_CLARIFICATION,
            clarification_reason="comparison member provenance unavailable",
        ),
        context_action="KEEP",
    )

    handoff = TypedHandoffRouter().route(resolution)

    assert handoff.route is HandoffRoute.CLARIFICATION
    assert handoff.target.clarification_reason == (
        "comparison member provenance unavailable"
    )


def test_single_object_is_rejected_from_handoff_boundary() -> None:
    resolution = TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope("drone-mini")
        ),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action="KEEP",
    )

    with pytest.raises(ValueError, match="Product Fact flow"):
        TypedHandoffRouter().route(resolution)
