"""Minimal Slice 3 conversation state reducer for target switching.

This module is intentionally internal to ``backend.conversation``.  It does
not extend the public TurnRequest or AnswerEnvelope wire contracts and it does
not persist dynamic commerce facts.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from backend.common import SCHEMA_VERSION, ObjectScope
from backend.common.contracts import WireModel
from backend.conversation.target_resolution import (
    ContextAction,
    TargetResolution,
    TurnTargetKind,
)

type SchemaVersion = Literal["1.0"]


class PendingSwitchTrigger(StrEnum):
    SYSTEM_DISAMBIGUATION = "SYSTEM_DISAMBIGUATION"
    USER_SWITCH_REQUEST = "USER_SWITCH_REQUEST"
    USER_CORRECTION = "USER_CORRECTION"


class PendingSwitchEffect(StrEnum):
    UPSERT = "UPSERT"
    CANCEL = "CANCEL"
    EXPIRE = "EXPIRE"


class StateTransitionStatus(StrEnum):
    APPLIED = "APPLIED"
    UNCHANGED = "UNCHANGED"
    REPLAYED = "REPLAYED"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    PENDING_SWITCH_CONFLICT = "PENDING_SWITCH_CONFLICT"


class StateChangeType(StrEnum):
    CONFIRMED_CONTEXT_SET = "CONFIRMED_CONTEXT_SET"
    PENDING_SWITCH_CREATED = "PENDING_SWITCH_CREATED"
    PENDING_SWITCH_REPLACED = "PENDING_SWITCH_REPLACED"
    PENDING_SWITCH_CANCELLED = "PENDING_SWITCH_CANCELLED"
    PENDING_SWITCH_EXPIRED = "PENDING_SWITCH_EXPIRED"
    PENDING_SWITCH_CONFIRMED = "PENDING_SWITCH_CONFIRMED"


class ConfirmedTargetContext(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    target: ObjectScope
    confirmed_by_message_id: str
    confirmed_at_revision: int = Field(ge=0)


class PendingTargetSwitch(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    target: ObjectScope
    created_by_message_id: str
    created_at_revision: int = Field(ge=0)
    expected_revision: int = Field(ge=0)
    trigger: PendingSwitchTrigger
    expires_after_turns: int = Field(default=1, ge=1)


class ConversationState(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    conversation_id: str
    revision: int = Field(default=0, ge=0)
    confirmed_context: ConfirmedTargetContext | None = None
    pending_switch: PendingTargetSwitch | None = None


class StateDiffEntry(WireModel):
    change_type: StateChangeType
    before: ObjectScope | None = None
    after: ObjectScope | None = None
    message_id: str


class StateDiff(WireModel):
    revision_before: int = Field(ge=0)
    revision_after: int = Field(ge=0)
    entries: tuple[StateDiffEntry, ...] = ()

    @model_validator(mode="after")
    def validate_revision_shape(self) -> StateDiff:
        if self.entries and self.revision_after != self.revision_before + 1:
            raise ValueError("state changes must advance revision exactly once")
        if not self.entries and self.revision_after != self.revision_before:
            raise ValueError("empty state diff must not advance revision")
        return self


class StateTransitionRequest(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    conversation_id: str
    message_id: str
    expected_revision: int = Field(ge=0)
    resolution: TargetResolution
    pending_switch_effect: PendingSwitchEffect = PendingSwitchEffect.UPSERT
    pending_switch_trigger: PendingSwitchTrigger = (
        PendingSwitchTrigger.USER_SWITCH_REQUEST
    )

    @model_validator(mode="after")
    def validate_request_shape(self) -> StateTransitionRequest:
        action = self.resolution.context_action
        if action is not ContextAction.AWAIT_CONFIRMATION and (
            "pending_switch_effect" in self.model_fields_set
            and self.pending_switch_effect is not PendingSwitchEffect.UPSERT
        ):
            raise ValueError("pending switch effects only apply to AWAIT_CONFIRMATION")
        return self


class StateTransitionResult(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    status: StateTransitionStatus
    state: ConversationState
    diff: StateDiff
    conflict_revision: int | None = None
    replay_of_message_id: str | None = None
    reason: str

    @model_validator(mode="after")
    def validate_result_invariants(self) -> StateTransitionResult:
        state_revision = self.state.revision
        if self.diff.revision_after != state_revision:
            raise ValueError("state revision must match diff revision_after")
        if self.status is StateTransitionStatus.APPLIED:
            if not self.diff.entries:
                raise ValueError("APPLIED requires a non-empty state diff")
            if self.diff.revision_after != self.diff.revision_before + 1:
                raise ValueError("APPLIED must advance revision exactly once")
        elif self.status is StateTransitionStatus.REPLAYED:
            if self.replay_of_message_id is None:
                raise ValueError("REPLAYED requires replay_of_message_id")
        else:
            if self.replay_of_message_id is not None:
                raise ValueError("only REPLAYED may use replay_of_message_id")
            if self.diff.entries:
                raise ValueError(
                    f"{self.status.value} must not carry state diff entries"
                )
            if self.diff.revision_before != self.diff.revision_after:
                raise ValueError(f"{self.status.value} must not change revision")
        if (
            self.status
            in {
                StateTransitionStatus.REVISION_CONFLICT,
                StateTransitionStatus.IDEMPOTENCY_CONFLICT,
                StateTransitionStatus.PENDING_SWITCH_CONFLICT,
            }
            and self.conflict_revision != state_revision
        ):
            raise ValueError("conflict results must expose the current state revision")
        if (
            self.status
            not in {
                StateTransitionStatus.REVISION_CONFLICT,
                StateTransitionStatus.IDEMPOTENCY_CONFLICT,
                StateTransitionStatus.PENDING_SWITCH_CONFLICT,
            }
            and self.conflict_revision is not None
        ):
            raise ValueError("only conflict results may carry conflict_revision")
        return self

    @property
    def applied(self) -> bool:
        return self.status is StateTransitionStatus.APPLIED


class _IdempotencyRecord(WireModel):
    message_id: str
    payload_digest: str
    result: StateTransitionResult


class InMemoryConversationStateRepository:
    """Replaceable in-memory repository for reducer tests and later adapters."""

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._message_records: dict[tuple[str, str], _IdempotencyRecord] = {}

    def get(self, conversation_id: str) -> ConversationState:
        return self._states.get(
            conversation_id, ConversationState(conversation_id=conversation_id)
        )

    def save(self, state: ConversationState) -> None:
        self._states[state.conversation_id] = state

    def apply(self, request: StateTransitionRequest) -> StateTransitionResult:
        key = (request.conversation_id, request.message_id)
        payload_digest = _payload_digest(request)
        existing = self._message_records.get(key)
        if existing is not None:
            if existing.payload_digest != payload_digest:
                current = self.get(request.conversation_id)
                return _unchanged_result(
                    status=StateTransitionStatus.IDEMPOTENCY_CONFLICT,
                    state=current,
                    reason="message_id was already used with a different payload",
                    conflict_revision=current.revision,
                )
            stored = existing.result
            return StateTransitionResult(
                status=(
                    StateTransitionStatus.REPLAYED
                    if stored.status
                    in {
                        StateTransitionStatus.APPLIED,
                        StateTransitionStatus.UNCHANGED,
                    }
                    else stored.status
                ),
                state=stored.state,
                diff=stored.diff,
                replay_of_message_id=(
                    request.message_id
                    if stored.status
                    in {
                        StateTransitionStatus.APPLIED,
                        StateTransitionStatus.UNCHANGED,
                    }
                    else None
                ),
                conflict_revision=stored.conflict_revision,
                reason=stored.reason,
            )

        current = self.get(request.conversation_id)
        result = reduce_conversation_state(current, request)
        if result.status in {
            StateTransitionStatus.APPLIED,
            StateTransitionStatus.UNCHANGED,
            StateTransitionStatus.REVISION_CONFLICT,
            StateTransitionStatus.PENDING_SWITCH_CONFLICT,
        }:
            self.save(result.state)
            self._message_records[key] = _IdempotencyRecord(
                message_id=request.message_id,
                payload_digest=payload_digest,
                result=result,
            )
        return result


def reduce_conversation_state(
    state: ConversationState, request: StateTransitionRequest
) -> StateTransitionResult:
    """Apply one target-resolution state transition with revision protection."""
    if state.conversation_id != request.conversation_id:
        raise ValueError("request conversation_id must match state")
    if request.expected_revision != state.revision:
        return _unchanged_result(
            status=StateTransitionStatus.REVISION_CONFLICT,
            state=state,
            reason="expected_revision is stale",
            conflict_revision=state.revision,
        )

    action = request.resolution.context_action
    if action is ContextAction.KEEP:
        return _unchanged_result(
            status=StateTransitionStatus.UNCHANGED,
            state=state,
            reason=(
                "KEEP leaves confirmed context, pending switch, and revision unchanged"
            ),
        )
    if action is ContextAction.AWAIT_CONFIRMATION:
        return _apply_pending_switch(state, request)
    return _apply_confirmed_switch(state, request)


def _apply_pending_switch(
    state: ConversationState, request: StateTransitionRequest
) -> StateTransitionResult:
    effect = request.pending_switch_effect
    if effect is PendingSwitchEffect.CANCEL:
        return _clear_pending_switch(
            state,
            message_id=request.message_id,
            change_type=StateChangeType.PENDING_SWITCH_CANCELLED,
            unchanged_reason="cancel requested with no pending switch",
        )
    if effect is PendingSwitchEffect.EXPIRE:
        return _clear_pending_switch(
            state,
            message_id=request.message_id,
            change_type=StateChangeType.PENDING_SWITCH_EXPIRED,
            unchanged_reason="expiration requested with no pending switch",
        )

    target = _single_object_scope(request.resolution)
    next_revision = state.revision + 1
    previous_pending = state.pending_switch
    next_pending = PendingTargetSwitch(
        target=target,
        created_by_message_id=request.message_id,
        created_at_revision=next_revision,
        expected_revision=next_revision,
        trigger=request.pending_switch_trigger,
    )
    change_type = (
        StateChangeType.PENDING_SWITCH_CREATED
        if previous_pending is None
        else StateChangeType.PENDING_SWITCH_REPLACED
    )
    next_state = ConversationState(
        conversation_id=state.conversation_id,
        revision=next_revision,
        confirmed_context=state.confirmed_context,
        pending_switch=next_pending,
    )
    return _applied_result(
        state=next_state,
        revision_before=state.revision,
        entry=StateDiffEntry(
            change_type=change_type,
            before=previous_pending.target if previous_pending is not None else None,
            after=target,
            message_id=request.message_id,
        ),
        reason="pending target switch updated",
    )


def _apply_confirmed_switch(
    state: ConversationState, request: StateTransitionRequest
) -> StateTransitionResult:
    target = _single_object_scope(request.resolution)
    if state.pending_switch is not None:
        if target != state.pending_switch.target:
            return _unchanged_result(
                status=StateTransitionStatus.PENDING_SWITCH_CONFLICT,
                state=state,
                reason="confirmed target does not match pending target switch",
                conflict_revision=state.revision,
            )
        if request.expected_revision != state.pending_switch.expected_revision:
            return _unchanged_result(
                status=StateTransitionStatus.PENDING_SWITCH_CONFLICT,
                state=state,
                reason="pending target switch expected_revision does not match",
                conflict_revision=state.revision,
            )
    next_revision = state.revision + 1
    confirmed = ConfirmedTargetContext(
        target=target,
        confirmed_by_message_id=request.message_id,
        confirmed_at_revision=next_revision,
    )
    entries = [
        StateDiffEntry(
            change_type=StateChangeType.CONFIRMED_CONTEXT_SET,
            before=(
                state.confirmed_context.target
                if state.confirmed_context is not None
                else None
            ),
            after=target,
            message_id=request.message_id,
        )
    ]
    if state.pending_switch is not None:
        entries.append(
            StateDiffEntry(
                change_type=StateChangeType.PENDING_SWITCH_CONFIRMED,
                before=state.pending_switch.target,
                after=None,
                message_id=request.message_id,
            )
        )
    next_state = ConversationState(
        conversation_id=state.conversation_id,
        revision=next_revision,
        confirmed_context=confirmed,
        pending_switch=None,
    )
    return StateTransitionResult(
        status=StateTransitionStatus.APPLIED,
        state=next_state,
        diff=StateDiff(
            revision_before=state.revision,
            revision_after=next_revision,
            entries=tuple(entries),
        ),
        reason="confirmed target context updated",
    )


def _clear_pending_switch(
    state: ConversationState,
    *,
    message_id: str,
    change_type: StateChangeType,
    unchanged_reason: str,
) -> StateTransitionResult:
    if state.pending_switch is None:
        return _unchanged_result(
            status=StateTransitionStatus.UNCHANGED,
            state=state,
            reason=unchanged_reason,
        )

    next_revision = state.revision + 1
    next_state = ConversationState(
        conversation_id=state.conversation_id,
        revision=next_revision,
        confirmed_context=state.confirmed_context,
        pending_switch=None,
    )
    return _applied_result(
        state=next_state,
        revision_before=state.revision,
        entry=StateDiffEntry(
            change_type=change_type,
            before=state.pending_switch.target,
            after=None,
            message_id=message_id,
        ),
        reason="pending target switch cleared",
    )


def _single_object_scope(resolution: TargetResolution) -> ObjectScope:
    if resolution.turn_target.kind is not TurnTargetKind.SINGLE_OBJECT:
        raise ValueError("state mutations require a SINGLE_OBJECT target")
    if resolution.turn_target.object_scope is None:
        raise ValueError("SINGLE_OBJECT target is missing object_scope")
    return resolution.turn_target.object_scope


def _applied_result(
    *,
    state: ConversationState,
    revision_before: int,
    entry: StateDiffEntry,
    reason: str,
) -> StateTransitionResult:
    return StateTransitionResult(
        status=StateTransitionStatus.APPLIED,
        state=state,
        diff=StateDiff(
            revision_before=revision_before,
            revision_after=state.revision,
            entries=(entry,),
        ),
        reason=reason,
    )


def _unchanged_result(
    *,
    status: StateTransitionStatus,
    state: ConversationState,
    reason: str,
    conflict_revision: int | None = None,
) -> StateTransitionResult:
    return StateTransitionResult(
        status=status,
        state=state,
        diff=StateDiff(
            revision_before=state.revision,
            revision_after=state.revision,
        ),
        conflict_revision=conflict_revision,
        reason=reason,
    )


def _payload_digest(request: StateTransitionRequest) -> str:
    payload = request.to_wire_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
