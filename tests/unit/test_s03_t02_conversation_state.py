"""S03-T02 reducer tests for minimal target-switch state semantics."""

import pytest
from pydantic import ValidationError

from backend.common import ObjectScope
from backend.conversation import (
    ContextAction,
    ConversationState,
    InMemoryConversationStateRepository,
    PendingSwitchEffect,
    PendingTargetSwitch,
    ResolutionSource,
    StateChangeType,
    StateDiff,
    StateTransitionRequest,
    StateTransitionResult,
    StateTransitionStatus,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)

pytestmark = pytest.mark.unit


def scope(product_id: str, variant_id: str | None = None) -> ObjectScope:
    return ObjectScope(
        store_id="store-s03-alpha",
        product_id=product_id,
        variant_id=variant_id,
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


def request(
    message_id: str,
    expected_revision: int,
    target_resolution: TargetResolution,
    *,
    effect: PendingSwitchEffect = PendingSwitchEffect.UPSERT,
) -> StateTransitionRequest:
    return StateTransitionRequest(
        conversation_id="conversation-s03",
        message_id=message_id,
        expected_revision=expected_revision,
        resolution=target_resolution,
        pending_switch_effect=effect,
    )


def test_keep_does_not_change_confirmed_pending_or_revision() -> None:
    repository = InMemoryConversationStateRepository()

    result = repository.apply(
        request("m-keep", 0, resolution("drone-mini", ContextAction.KEEP))
    )

    assert result.status is StateTransitionStatus.UNCHANGED
    assert result.state.revision == 0
    assert result.state.confirmed_context is None
    assert result.state.pending_switch is None
    assert result.diff.entries == ()


def test_await_confirmation_creates_pending_switch_with_one_revision() -> None:
    repository = InMemoryConversationStateRepository()

    result = repository.apply(
        request("m-await", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION))
    )

    assert result.status is StateTransitionStatus.APPLIED
    assert result.state.revision == 1
    assert result.state.confirmed_context is None
    assert result.state.pending_switch is not None
    assert result.state.pending_switch.target == scope("drone-air")
    assert result.state.pending_switch.expected_revision == 1
    assert [entry.change_type for entry in result.diff.entries] == [
        StateChangeType.PENDING_SWITCH_CREATED
    ]


def test_await_confirmation_replaces_pending_switch_with_one_revision() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request(
            "m-await-1", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION)
        )
    )

    result = repository.apply(
        request(
            "m-await-2",
            1,
            resolution("drone-cine", ContextAction.AWAIT_CONFIRMATION),
        )
    )

    assert result.status is StateTransitionStatus.APPLIED
    assert result.state.revision == 2
    assert result.state.pending_switch is not None
    assert result.state.pending_switch.target == scope("drone-cine")
    assert result.diff.entries[0].change_type is StateChangeType.PENDING_SWITCH_REPLACED
    assert result.diff.entries[0].before == scope("drone-air")
    assert result.diff.entries[0].after == scope("drone-cine")


def test_await_confirmation_cancels_pending_switch_with_one_revision() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request("m-await", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION))
    )

    result = repository.apply(
        request(
            "m-cancel",
            1,
            resolution("drone-air", ContextAction.AWAIT_CONFIRMATION),
            effect=PendingSwitchEffect.CANCEL,
        )
    )

    assert result.status is StateTransitionStatus.APPLIED
    assert result.state.revision == 2
    assert result.state.pending_switch is None
    assert (
        result.diff.entries[0].change_type is StateChangeType.PENDING_SWITCH_CANCELLED
    )


def test_pending_switch_expiration_is_replayable_and_revisioned() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request("m-await", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION))
    )

    result = repository.apply(
        request(
            "m-expire",
            1,
            resolution("drone-air", ContextAction.AWAIT_CONFIRMATION),
            effect=PendingSwitchEffect.EXPIRE,
        )
    )

    assert result.status is StateTransitionStatus.APPLIED
    assert result.state.revision == 2
    assert result.state.pending_switch is None
    assert result.diff.entries[0].change_type is StateChangeType.PENDING_SWITCH_EXPIRED


def test_confirmed_switch_updates_context_and_clears_pending_once() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request("m-await", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION))
    )

    result = repository.apply(
        request(
            "m-confirm",
            1,
            resolution("drone-air", ContextAction.SWITCH_CONFIRMED),
        )
    )

    assert result.status is StateTransitionStatus.APPLIED
    assert result.state.revision == 2
    assert result.state.confirmed_context is not None
    assert result.state.confirmed_context.target == scope("drone-air")
    assert result.state.confirmed_context.confirmed_at_revision == 2
    assert result.state.pending_switch is None
    assert [entry.change_type for entry in result.diff.entries] == [
        StateChangeType.CONFIRMED_CONTEXT_SET,
        StateChangeType.PENDING_SWITCH_CONFIRMED,
    ]


def test_confirmed_switch_must_match_pending_target() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request("m-await", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION))
    )

    result = repository.apply(
        request(
            "m-confirm-wrong-target",
            1,
            resolution("drone-mini", ContextAction.SWITCH_CONFIRMED),
        )
    )

    assert result.status is StateTransitionStatus.PENDING_SWITCH_CONFLICT
    assert result.state.revision == 1
    assert result.state.confirmed_context is None
    assert result.state.pending_switch is not None
    assert result.state.pending_switch.target == scope("drone-air")


def test_confirmed_switch_must_match_pending_expected_revision() -> None:
    repository = InMemoryConversationStateRepository()
    repository.save(
        ConversationState(
            conversation_id="conversation-s03",
            revision=2,
            pending_switch=PendingTargetSwitch(
                target=scope("drone-air"),
                created_by_message_id="m-await",
                created_at_revision=1,
                expected_revision=1,
                trigger="USER_SWITCH_REQUEST",
            ),
        )
    )

    result = repository.apply(
        request(
            "m-confirm-stale-pending",
            2,
            resolution("drone-air", ContextAction.SWITCH_CONFIRMED),
        )
    )

    assert result.status is StateTransitionStatus.PENDING_SWITCH_CONFLICT
    assert result.state.revision == 2
    assert result.state.confirmed_context is None
    assert result.state.pending_switch is not None
    assert result.state.pending_switch.expected_revision == 1


def test_duplicate_message_with_same_payload_replays_first_result() -> None:
    repository = InMemoryConversationStateRepository()
    first_request = request(
        "m-await", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION)
    )

    first = repository.apply(first_request)
    replay = repository.apply(first_request)

    assert first.status is StateTransitionStatus.APPLIED
    assert replay.status is StateTransitionStatus.REPLAYED
    assert replay.replay_of_message_id == "m-await"
    assert replay.state.revision == 1
    assert repository.get("conversation-s03").revision == 1


def test_duplicate_message_with_different_payload_fails_closed() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request("m-dup", 0, resolution("drone-air", ContextAction.AWAIT_CONFIRMATION))
    )

    result = repository.apply(
        request("m-dup", 1, resolution("drone-cine", ContextAction.AWAIT_CONFIRMATION))
    )

    assert result.status is StateTransitionStatus.IDEMPOTENCY_CONFLICT
    assert result.state.revision == 1
    assert result.state.pending_switch is not None
    assert result.state.pending_switch.target == scope("drone-air")


def test_stale_expected_revision_returns_recoverable_conflict_without_overwrite() -> (
    None
):
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request(
            "m-confirm",
            0,
            resolution("drone-mini", ContextAction.SWITCH_CONFIRMED),
        )
    )

    result = repository.apply(
        request("m-stale", 0, resolution("drone-air", ContextAction.SWITCH_CONFIRMED))
    )

    assert result.status is StateTransitionStatus.REVISION_CONFLICT
    assert result.conflict_revision == 1
    assert result.state.revision == 1
    assert result.state.confirmed_context is not None
    assert result.state.confirmed_context.target == scope("drone-mini")


def test_stale_revision_result_is_idempotency_recorded() -> None:
    repository = InMemoryConversationStateRepository()
    repository.apply(
        request(
            "m-confirm",
            0,
            resolution("drone-mini", ContextAction.SWITCH_CONFIRMED),
        )
    )
    stale_request = request(
        "m-stale-recorded", 0, resolution("drone-air", ContextAction.SWITCH_CONFIRMED)
    )

    first = repository.apply(stale_request)
    retry = repository.apply(stale_request)
    conflict = repository.apply(
        request(
            "m-stale-recorded",
            1,
            resolution("drone-air", ContextAction.SWITCH_CONFIRMED),
        )
    )

    assert first.status is StateTransitionStatus.REVISION_CONFLICT
    assert retry.status is StateTransitionStatus.REVISION_CONFLICT
    assert retry == first
    assert conflict.status is StateTransitionStatus.IDEMPOTENCY_CONFLICT
    assert repository.get("conversation-s03").confirmed_context is not None
    assert repository.get("conversation-s03").confirmed_context.target == scope(
        "drone-mini"
    )


def test_state_transition_result_rejects_applied_with_empty_diff() -> None:
    with pytest.raises(ValidationError):
        StateTransitionResult(
            status=StateTransitionStatus.APPLIED,
            state=ConversationState(conversation_id="conversation-s03", revision=0),
            diff=StateDiff(revision_before=0, revision_after=0),
            reason="invalid applied result",
        )


def test_state_transition_result_rejects_applied_with_replay_message_id() -> None:
    with pytest.raises(ValidationError):
        StateTransitionResult(
            status=StateTransitionStatus.APPLIED,
            state=ConversationState(conversation_id="conversation-s03", revision=1),
            diff=StateDiff(
                revision_before=0,
                revision_after=1,
                entries=(
                    {
                        "change_type": "CONFIRMED_CONTEXT_SET",
                        "after": scope("drone-air"),
                        "message_id": "m-invalid",
                    },
                ),
            ),
            replay_of_message_id="m-original",
            reason="invalid applied result",
        )


def test_state_transition_result_rejects_conflict_with_state_diff() -> None:
    with pytest.raises(ValidationError):
        StateTransitionResult(
            status=StateTransitionStatus.REVISION_CONFLICT,
            state=ConversationState(conversation_id="conversation-s03", revision=1),
            diff=StateDiff(
                revision_before=0,
                revision_after=1,
                entries=(
                    {
                        "change_type": "CONFIRMED_CONTEXT_SET",
                        "after": scope("drone-air"),
                        "message_id": "m-invalid",
                    },
                ),
            ),
            conflict_revision=1,
            reason="invalid conflict result",
        )


def test_models_forbid_dynamic_commerce_facts() -> None:
    with pytest.raises(ValidationError):
        # Dynamic price/inventory/sellable fields are not part of S03-T02 state.
        StateTransitionRequest.model_validate(
            {
                "conversation_id": "conversation-s03",
                "message_id": "m-dynamic",
                "expected_revision": 0,
                "resolution": resolution(
                    "drone-mini", ContextAction.SWITCH_CONFIRMED
                ).to_wire(),
                "price": 4999,
            }
        )
