"""S03-T02 contract checks for internal revision and idempotency semantics."""

import json

import pytest
from pydantic import ValidationError

from backend.common import ObjectScope, TurnRequest
from backend.conversation import (
    ContextAction,
    ConversationState,
    InMemoryConversationStateRepository,
    PendingSwitchEffect,
    ResolutionSource,
    StateDiff,
    StateTransitionRequest,
    StateTransitionResult,
    StateTransitionStatus,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)

pytestmark = pytest.mark.contract


def scope(product_id: str) -> ObjectScope:
    return ObjectScope(
        store_id="store-s03-alpha",
        product_id=product_id,
    )


def resolution(product_id: str, action: ContextAction) -> TargetResolution:
    return TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.SINGLE_OBJECT,
            object_scope=scope(product_id),
        ),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=action,
    )


def transition(
    message_id: str,
    expected_revision: int,
    action: ContextAction,
    product_id: str = "drone-air",
) -> StateTransitionRequest:
    return StateTransitionRequest(
        conversation_id="conversation-s03",
        message_id=message_id,
        expected_revision=expected_revision,
        resolution=resolution(product_id, action),
    )


def test_state_reducer_wire_round_trip_is_internal_and_versioned() -> None:
    request = transition("m-confirm", 0, ContextAction.SWITCH_CONFIRMED)
    result = InMemoryConversationStateRepository().apply(request)

    assert StateTransitionRequest.model_validate_json(request.to_wire_json()) == request
    assert result.model_validate_json(result.to_wire_json()) == result
    assert result.to_wire()["schema_version"] == "1.0"
    assert result.state.to_wire()["schema_version"] == "1.0"


def test_state_transition_result_rejects_invalid_wire_invariants() -> None:
    with pytest.raises(ValidationError):
        StateTransitionResult.model_validate(
            {
                "status": "APPLIED",
                "state": {"conversation_id": "conversation-s03", "revision": 0},
                "diff": {"revision_before": 0, "revision_after": 0, "entries": []},
                "reason": "invalid applied result",
            }
        )

    valid_conflict = StateTransitionResult(
        status=StateTransitionStatus.REVISION_CONFLICT,
        state=ConversationState(conversation_id="conversation-s03", revision=1),
        diff=StateDiff(revision_before=1, revision_after=1),
        conflict_revision=1,
        reason="expected_revision is stale",
    )

    assert (
        StateTransitionResult.model_validate_json(valid_conflict.to_wire_json())
        == valid_conflict
    )


def test_state_reducer_does_not_expand_public_turn_request_contract() -> None:
    turn_schema = TurnRequest.model_json_schema()
    schema_text = json.dumps(turn_schema)

    assert "expected_revision" not in schema_text
    assert "resulting_revision" not in schema_text
    assert "pending_switch" not in schema_text
    assert "confirmed_context" not in schema_text


def test_stale_revision_and_duplicate_message_contract_cases() -> None:
    repository = InMemoryConversationStateRepository()
    first_request = transition("m-await", 0, ContextAction.AWAIT_CONFIRMATION)

    first = repository.apply(first_request)
    replay = repository.apply(first_request)
    stale = repository.apply(transition("m-stale", 0, ContextAction.SWITCH_CONFIRMED))
    conflict = repository.apply(
        StateTransitionRequest(
            conversation_id="conversation-s03",
            message_id="m-await",
            expected_revision=1,
            resolution=resolution("drone-mini", ContextAction.AWAIT_CONFIRMATION),
        )
    )

    assert first.status is StateTransitionStatus.APPLIED
    assert replay.status is StateTransitionStatus.REPLAYED
    assert stale.status is StateTransitionStatus.REVISION_CONFLICT
    assert stale.conflict_revision == 1
    assert conflict.status is StateTransitionStatus.IDEMPOTENCY_CONFLICT
    assert repository.get("conversation-s03").revision == 1
    assert repository.get("conversation-s03").pending_switch is not None
    assert repository.get("conversation-s03").pending_switch.target == scope(
        "drone-air"
    )


def test_negative_confirmation_clears_pending_without_confirming_context() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(transition("m-await", 0, ContextAction.AWAIT_CONFIRMATION))

    result = repository.apply(
        StateTransitionRequest(
            conversation_id="conversation-s03",
            message_id="m-no",
            expected_revision=1,
            resolution=resolution("drone-air", ContextAction.AWAIT_CONFIRMATION),
            pending_switch_effect=PendingSwitchEffect.CANCEL,
        )
    )

    assert result.status is StateTransitionStatus.APPLIED
    assert result.state.revision == 2
    assert result.state.confirmed_context is None
    assert result.state.pending_switch is None
