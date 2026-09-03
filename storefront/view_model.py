"""Storefront-local view models derived from existing public responses."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from backend.api import ConversationTransportError
from backend.common import (
    SCHEMA_VERSION,
    TURN_REQUEST_VALIDATION_HTTP_STATUS,
    AnswerEnvelope,
    AnswerPayload,
    FallbackPayload,
    FallbackReasonCode,
    InternalDiagnosticCode,
    ObjectScope,
    ProductCard,
    StandardFallback,
    TurnRequestValidationResponse,
)
from backend.common.contracts import ConversationStateProjection, WireModel
from backend.conversation import (
    NormalizedConstraint,
    PendingTargetSwitch,
)

type SchemaVersion = Literal["1.0"]


class RenderStatus(StrEnum):
    ANSWER = "ANSWER"
    FALLBACK = "FALLBACK"
    TRANSPORT_REJECTION = "TRANSPORT_REJECTION"


class StorefrontPendingClarification(WireModel):
    """Local display state for a server-confirmed pending clarification."""

    prompt: str
    source_message_id: str
    consecutive_count: int = Field(ge=1, le=2)


class StorefrontUiState(WireModel):
    """Local UI state that is already confirmed by server-side turn handling."""

    active_constraints: tuple[NormalizedConstraint, ...] = ()
    pending_clarification: StorefrontPendingClarification | None = None
    pending_target_switch: PendingTargetSwitch | None = None
    submitting: bool = False


class ConstraintPresentationState(WireModel):
    """Constraints and pending actions visible to the storefront."""

    active_constraints: tuple[NormalizedConstraint, ...] = ()
    pending_clarification: StorefrontPendingClarification | None = None
    pending_target_switch: PendingTargetSwitch | None = None
    revision: int = Field(default=0, ge=0)
    submitting: bool = False


class StorefrontTargetDisplay(WireModel):
    """Resolved target display derived from envelope scope and optional card."""

    scope: ObjectScope
    title: str


class FallbackView(WireModel):
    """Public fallback fields safe for direct storefront rendering."""

    reason_code: FallbackReasonCode
    message: str
    retryable: bool
    next_actions: tuple[str, ...]
    resolved_scope: ObjectScope | None = None


class StorefrontTurnView(WireModel):
    """Internal view of one accepted application turn."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    render_status: Literal[RenderStatus.ANSWER, RenderStatus.FALLBACK]
    trace_correlation_id: str
    target: StorefrontTargetDisplay
    constraint_state: ConstraintPresentationState
    answer: AnswerPayload | None = None
    fallback: FallbackView | None = None

    @model_validator(mode="after")
    def validate_one_to_one_payload(self) -> "StorefrontTurnView":
        if self.render_status is RenderStatus.ANSWER:
            if self.answer is None or self.fallback is not None:
                raise ValueError("ANSWER views require exactly one answer payload")
        if self.render_status is RenderStatus.FALLBACK:
            if self.fallback is None or self.answer is not None:
                raise ValueError("FALLBACK views require exactly one fallback view")
        return self


class StorefrontTransportRejection(WireModel):
    """Storefront display state for HTTP validation rejection, not fallback."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    render_status: Literal[RenderStatus.TRANSPORT_REJECTION] = (
        RenderStatus.TRANSPORT_REJECTION
    )
    status_code: int
    error_code: str | None = None
    message: str


def build_storefront_turn_view(
    envelope: AnswerEnvelope,
    *,
    ui_state: StorefrontUiState | None = None,
) -> StorefrontTurnView:
    """Derive the local storefront view from a public accepted-turn envelope."""
    payload = envelope.root
    state = ui_state or StorefrontUiState()
    constraint_state = _constraint_state_from_envelope(
        payload.conversation_state,
        fallback_state=state,
    )
    target = StorefrontTargetDisplay(
        scope=payload.resolved_scope,
        title=_target_title(payload.resolved_scope, payload.product_card),
    )

    if isinstance(payload, AnswerPayload):
        _assert_no_internal_diagnostics(payload.text)
        return StorefrontTurnView(
            render_status=RenderStatus.ANSWER,
            trace_correlation_id=payload.trace_correlation_id,
            target=target,
            constraint_state=constraint_state,
            answer=payload,
        )

    fallback = _fallback_view(payload)
    return StorefrontTurnView(
        render_status=RenderStatus.FALLBACK,
        trace_correlation_id=payload.trace_correlation_id,
        target=target,
        constraint_state=constraint_state,
        fallback=fallback,
    )


def build_transport_rejection_view(
    error: ConversationTransportError,
) -> StorefrontTransportRejection:
    """Render a rejected request separately from application fallback."""
    response = error.response
    return StorefrontTransportRejection(
        status_code=error.status_code,
        error_code=response.error_code if response is not None else None,
        message=(
            response.message
            if response is not None
            else "Conversation request was rejected before application handling."
        ),
    )


def _fallback_view(payload: FallbackPayload) -> FallbackView:
    fallback = payload.fallback
    _assert_fallback_matches_payload(payload, fallback)
    fallback_copy = f"{fallback.message} {' '.join(fallback.next_actions)}"
    _assert_no_internal_diagnostics(fallback_copy)
    return FallbackView(
        reason_code=fallback.reason_code,
        message=fallback.message,
        retryable=fallback.retryable,
        next_actions=tuple(fallback.next_actions),
        resolved_scope=fallback.resolved_scope,
    )


def _constraint_state_from_envelope(
    conversation_state: ConversationStateProjection | None,
    *,
    fallback_state: StorefrontUiState,
) -> ConstraintPresentationState:
    """Use accepted server state when supplied; UI state is legacy display-only."""
    if conversation_state is None:
        return ConstraintPresentationState(
            active_constraints=fallback_state.active_constraints,
            pending_clarification=fallback_state.pending_clarification,
            pending_target_switch=fallback_state.pending_target_switch,
            submitting=fallback_state.submitting,
        )
    try:
        return ConstraintPresentationState(
            active_constraints=tuple(
                NormalizedConstraint.model_validate(item)
                for item in conversation_state.active_constraints
            ),
            pending_clarification=(
                StorefrontPendingClarification.model_validate(
                    conversation_state.pending_clarification
                )
                if conversation_state.pending_clarification is not None
                else None
            ),
            pending_target_switch=(
                PendingTargetSwitch.model_validate(conversation_state.pending_switch)
                if conversation_state.pending_switch is not None
                else None
            ),
            revision=conversation_state.revision,
            submitting=fallback_state.submitting,
        )
    except ValueError as error:
        raise ValueError("invalid server conversation_state projection") from error


def _assert_fallback_matches_payload(
    payload: FallbackPayload, fallback: StandardFallback
) -> None:
    if payload.text != fallback.message:
        raise ValueError("fallback message must match envelope text")
    if (
        fallback.resolved_scope is not None
        and fallback.resolved_scope != payload.resolved_scope
    ):
        raise ValueError("fallback scope must match envelope scope")


def _target_title(scope: ObjectScope, product_card: ProductCard | None) -> str:
    if product_card is None:
        return _scope_title(scope)
    if (
        product_card.store_id,
        product_card.product_id,
        product_card.variant_id,
    ) != (scope.store_id, scope.product_id, scope.variant_id):
        raise ValueError("product card scope must match resolved scope")
    return product_card.display_title


def _scope_title(scope: ObjectScope) -> str:
    if scope.variant_id is None:
        return scope.product_id
    return f"{scope.product_id} / {scope.variant_id}"


def _assert_no_internal_diagnostics(text: str) -> None:
    diagnostic_values = {code.value for code in InternalDiagnosticCode}
    if any(value in text for value in diagnostic_values):
        raise ValueError("storefront view must not expose internal diagnostics")


def validation_rejection_to_view(
    response: TurnRequestValidationResponse,
) -> StorefrontTransportRejection:
    """Build a transport rejection view directly from the public 422 body."""
    return StorefrontTransportRejection(
        status_code=TURN_REQUEST_VALIDATION_HTTP_STATUS,
        error_code=response.error_code,
        message=response.message,
    )
