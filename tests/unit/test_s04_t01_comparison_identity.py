"""S04-T01 comparison identity remains isolated from conversation state."""

import pytest

from backend.common import ObjectScope
from backend.conversation import (
    ComparisonMember,
    ContextAction,
    ConversationState,
    ResolutionSource,
    StateTransitionRequest,
    StateTransitionStatus,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
    reduce_conversation_state,
)

pytestmark = pytest.mark.unit


def scope(product_id: str, variant_id: str) -> ObjectScope:
    return ObjectScope(
        store_id="store-drone-cn",
        product_id=product_id,
        variant_id=variant_id,
    )


def test_comparison_resolution_keep_does_not_mutate_conversation_state() -> None:
    state = ConversationState(conversation_id="conversation-s04", revision=3)
    resolution = TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.COMPARISON_SET,
            comparison_members=(
                ComparisonMember(
                    scope=scope("9278439686282", "51492095623306"),
                    provenance=ResolutionSource.EXPLICIT,
                ),
                ComparisonMember(
                    scope=scope("9278460821642", "51492157456522"),
                    provenance=ResolutionSource.CONFIRMED_CONTEXT,
                ),
            ),
        ),
        context_action=ContextAction.KEEP,
    )

    result = reduce_conversation_state(
        state,
        StateTransitionRequest(
            conversation_id=state.conversation_id,
            message_id="message-s04-comparison",
            expected_revision=state.revision,
            resolution=resolution,
        ),
    )

    assert result.status is StateTransitionStatus.UNCHANGED
    assert result.state == state
    assert result.state.revision == 3
    assert result.state.confirmed_context is None
    assert result.state.pending_switch is None
