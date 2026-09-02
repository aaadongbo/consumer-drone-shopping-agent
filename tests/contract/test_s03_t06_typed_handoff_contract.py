"""S03-T06 handoff serialization and route/target shape contracts."""

import pytest

from backend.common import ObjectScope
from backend.conversation import (
    ComparisonMember,
    HandoffRoute,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
    TypedHandoff,
    TypedHandoffRouter,
)

pytestmark = pytest.mark.contract


def test_handoff_round_trip_is_strict_and_non_executing() -> None:
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            ComparisonMember(
                scope=ObjectScope(store_id="store-s03-alpha", product_id="drone-mini"),
                provenance=ResolutionSource.PAGE_CONTEXT,
            ),
            ComparisonMember(
                scope=ObjectScope(
                    store_id="store-s03-alpha", product_id="drone-cinema"
                ),
                provenance=ResolutionSource.EXPLICIT,
            ),
        ),
    )
    handoff = TypedHandoffRouter().route(
        TargetResolution(turn_target=target, context_action="KEEP")
    )

    restored = TypedHandoff.model_validate_json(handoff.to_wire_json())

    assert restored == handoff
    assert restored.route is HandoffRoute.COMPARISON
    assert restored.downstream_execution_allowed is False
    assert restored.target.object_scope is None
