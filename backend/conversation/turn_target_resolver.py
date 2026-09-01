"""Deterministic Slice 3 precedence and switch-resolution boundary.

The caller supplies already-extracted explicit references and turn intent.  This
module deliberately does not parse natural language, read commerce facts, or
mutate state; it produces a ``TargetResolution`` plus the exact reducer request
that a caller may apply once.
"""

from enum import StrEnum

from backend.catalog.target_references import (
    CatalogReferenceResolver,
    ExplicitReference,
    ReferenceResolutionStatus,
)
from backend.common import ObjectScope
from backend.common.contracts import WireModel
from backend.conversation.state import (
    ConversationState,
    PendingSwitchEffect,
    StateTransitionRequest,
)
from backend.conversation.target_resolution import (
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)


class TurnIntent(StrEnum):
    FACT_QUERY = "FACT_QUERY"
    EXPLICIT_SWITCH = "EXPLICIT_SWITCH"
    CONFIRM_PENDING_SWITCH = "CONFIRM_PENDING_SWITCH"
    DECLINE_PENDING_SWITCH = "DECLINE_PENDING_SWITCH"
    EXPIRE_PENDING_SWITCH = "EXPIRE_PENDING_SWITCH"


class ResolutionReason(StrEnum):
    EXPLICIT_REFERENCE = "EXPLICIT_REFERENCE"
    CONFIRMED_CONTEXT = "CONFIRMED_CONTEXT"
    PAGE_CONTEXT = "PAGE_CONTEXT"
    EXPLICIT_REFERENCE_UNRESOLVED = "EXPLICIT_REFERENCE_UNRESOLVED"
    NO_CONTEXT = "NO_CONTEXT"
    PENDING_SWITCH_CONFIRMED = "PENDING_SWITCH_CONFIRMED"
    PENDING_SWITCH_CANCELLED = "PENDING_SWITCH_CANCELLED"
    PENDING_SWITCH_EXPIRED = "PENDING_SWITCH_EXPIRED"
    PENDING_SWITCH_MISSING = "PENDING_SWITCH_MISSING"
    CROSS_STORE_CONTEXT = "CROSS_STORE_CONTEXT"


class TurnTargetResolutionInput(WireModel):
    conversation_id: str
    message_id: str
    expected_revision: int
    page_scope: ObjectScope | None = None
    explicit_reference: ExplicitReference | None = None
    intent: TurnIntent = TurnIntent.FACT_QUERY


class TurnTargetResolutionOutcome(WireModel):
    resolution: TargetResolution
    reason: ResolutionReason
    state_patch: StateTransitionRequest | None = None


class TurnTargetResolver:
    """Apply explicit > confirmed > page precedence for one catalog store."""

    def __init__(self, *, catalog_resolver: CatalogReferenceResolver) -> None:
        self._catalog_resolver = catalog_resolver

    def resolve(
        self,
        *,
        request: TurnTargetResolutionInput,
        state: ConversationState,
    ) -> TurnTargetResolutionOutcome:
        if state.conversation_id != request.conversation_id:
            raise ValueError("request conversation_id must match conversation state")
        if any(
            scope.store_id != self._catalog_resolver.store_id
            for scope in (
                scope
                for scope in (
                    request.page_scope,
                    state.confirmed_context.target
                    if state.confirmed_context is not None
                    else None,
                    state.pending_switch.target
                    if state.pending_switch is not None
                    else None,
                )
                if scope is not None
            )
        ):
            return self._clarification(ResolutionReason.CROSS_STORE_CONTEXT)
        if request.intent in {
            TurnIntent.CONFIRM_PENDING_SWITCH,
            TurnIntent.DECLINE_PENDING_SWITCH,
            TurnIntent.EXPIRE_PENDING_SWITCH,
        }:
            return self._resolve_pending_action(request=request, state=state)

        if request.explicit_reference is not None:
            explicit = self._catalog_resolver.resolve(request.explicit_reference)
            if explicit.status is not ReferenceResolutionStatus.RESOLVED:
                return self._clarification(
                    ResolutionReason.EXPLICIT_REFERENCE_UNRESOLVED,
                    candidates=explicit.candidates,
                    clarification_reason=explicit.clarification_reason.value,
                )
            assert explicit.scope is not None
            action = (
                ContextAction.SWITCH_CONFIRMED
                if request.intent is TurnIntent.EXPLICIT_SWITCH
                else ContextAction.KEEP
            )
            return self._resolved(
                scope=explicit.scope,
                source=ResolutionSource.EXPLICIT,
                action=action,
                reason=ResolutionReason.EXPLICIT_REFERENCE,
                request=request,
            )

        confirmed = state.confirmed_context
        if confirmed is not None:
            return self._resolved(
                scope=confirmed.target,
                source=ResolutionSource.CONFIRMED_CONTEXT,
                action=ContextAction.KEEP,
                reason=ResolutionReason.CONFIRMED_CONTEXT,
                request=request,
            )
        if request.page_scope is not None:
            return self._resolved(
                scope=request.page_scope,
                source=ResolutionSource.PAGE_CONTEXT,
                action=ContextAction.KEEP,
                reason=ResolutionReason.PAGE_CONTEXT,
                request=request,
            )
        return self._clarification(ResolutionReason.NO_CONTEXT)

    def _resolve_pending_action(
        self,
        *,
        request: TurnTargetResolutionInput,
        state: ConversationState,
    ) -> TurnTargetResolutionOutcome:
        pending = state.pending_switch
        if pending is None:
            return self._clarification(ResolutionReason.PENDING_SWITCH_MISSING)
        if request.intent is TurnIntent.CONFIRM_PENDING_SWITCH:
            return self._resolved(
                scope=pending.target,
                source=ResolutionSource.EXPLICIT,
                action=ContextAction.SWITCH_CONFIRMED,
                reason=ResolutionReason.PENDING_SWITCH_CONFIRMED,
                request=request,
            )
        effect = (
            PendingSwitchEffect.CANCEL
            if request.intent is TurnIntent.DECLINE_PENDING_SWITCH
            else PendingSwitchEffect.EXPIRE
        )
        reason = (
            ResolutionReason.PENDING_SWITCH_CANCELLED
            if effect is PendingSwitchEffect.CANCEL
            else ResolutionReason.PENDING_SWITCH_EXPIRED
        )
        return self._resolved(
            scope=pending.target,
            source=ResolutionSource.EXPLICIT,
            action=ContextAction.AWAIT_CONFIRMATION,
            reason=reason,
            request=request,
            pending_switch_effect=effect,
        )

    @staticmethod
    def _resolved(
        *,
        scope: ObjectScope,
        source: ResolutionSource,
        action: ContextAction,
        reason: ResolutionReason,
        request: TurnTargetResolutionInput,
        pending_switch_effect: PendingSwitchEffect = PendingSwitchEffect.UPSERT,
    ) -> TurnTargetResolutionOutcome:
        resolution = TargetResolution(
            explicit_references=(scope,) if source is ResolutionSource.EXPLICIT else (),
            turn_target=TurnTarget(
                kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope
            ),
            resolution_source=source,
            context_action=action,
        )
        return TurnTargetResolutionOutcome(
            resolution=resolution,
            reason=reason,
            state_patch=StateTransitionRequest(
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                expected_revision=request.expected_revision,
                resolution=resolution,
                pending_switch_effect=pending_switch_effect,
            ),
        )

    @staticmethod
    def _clarification(
        reason: ResolutionReason,
        *,
        candidates: tuple[ObjectScope, ...] = (),
        clarification_reason: str | None = None,
    ) -> TurnTargetResolutionOutcome:
        resolution = TargetResolution(
            turn_target=TurnTarget(
                kind=TurnTargetKind.NEEDS_CLARIFICATION,
                clarification_reason=clarification_reason or reason.value,
                clarification_candidates=candidates,
            ),
            context_action=ContextAction.KEEP,
        )
        return TurnTargetResolutionOutcome(resolution=resolution, reason=reason)
