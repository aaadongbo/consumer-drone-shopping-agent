"""S03-T06 boundary journeys never enter the Product Fact flow."""

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

pytestmark = pytest.mark.e2e


def test_comparison_recommendation_and_support_have_distinct_handoff_routes() -> None:
    router = TypedHandoffRouter()
    comparison = router.route(
        TargetResolution(
            turn_target=TurnTarget(
                kind=TurnTargetKind.COMPARISON_SET,
                comparison_members=(
                    ComparisonMember(
                        scope=ObjectScope(
                            store_id="store-s03-alpha", product_id="drone-mini"
                        ),
                        provenance=ResolutionSource.EXPLICIT,
                    ),
                    ComparisonMember(
                        scope=ObjectScope(
                            store_id="store-s03-alpha", product_id="drone-cinema"
                        ),
                        provenance=ResolutionSource.EXPLICIT,
                    ),
                ),
            ),
            context_action="KEEP",
        )
    )
    recommendation = router.route(
        TargetResolution(
            turn_target=TurnTarget(kind=TurnTargetKind.RECOMMENDATION_TASK),
            context_action="KEEP",
        )
    )
    support = router.route(
        TargetResolution(
            turn_target=TurnTarget(kind=TurnTargetKind.STORE_SUPPORT),
            context_action="KEEP",
        )
    )

    assert (comparison.route, recommendation.route, support.route) == (
        HandoffRoute.COMPARISON,
        HandoffRoute.RECOMMENDATION,
        HandoffRoute.STORE_SUPPORT,
    )
    assert all(
        handoff.downstream_execution_allowed is False
        for handoff in (comparison, recommendation, support)
    )
