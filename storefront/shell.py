"""Minimal local shell state; it never becomes a conversation authority."""

from dataclasses import dataclass
from enum import StrEnum

from storefront.view_model import StorefrontTurnView


class StorefrontUserAction(StrEnum):
    RETRY = "RETRY"
    CLARIFY = "CLARIFY"
    SWITCH = "SWITCH"
    CONSTRAINT_EDIT = "CONSTRAINT_EDIT"
    CONSTRAINT_WITHDRAW = "CONSTRAINT_WITHDRAW"
    CONSTRAINT_SKIP = "CONSTRAINT_SKIP"


@dataclass(frozen=True)
class StorefrontActionRequest:
    """A user gesture for the existing server-side turn path, not a mutation."""

    action: StorefrontUserAction


@dataclass(frozen=True)
class StorefrontShellState:
    current_turn: StorefrontTurnView | None = None
    submitting: bool = False
    pending_action: StorefrontActionRequest | None = None


class MinimalStorefrontShell:
    """Presentation-only state transition boundary for the T03 storefront."""

    def __init__(self) -> None:
        self._state = StorefrontShellState()

    @property
    def state(self) -> StorefrontShellState:
        return self._state

    def begin_submit(self) -> None:
        # A new turn must not render a prior turn as current fact while loading.
        self._state = StorefrontShellState(submitting=True)

    def accept_server_turn(self, turn: StorefrontTurnView) -> None:
        """Render only a server-confirmed view-model from the existing adapter."""
        self._state = StorefrontShellState(current_turn=turn)

    def request_user_action(self, action: StorefrontUserAction) -> None:
        """Queue a user gesture without changing target or constraint authority."""
        if action is StorefrontUserAction.RETRY:
            turn = self._state.current_turn
            if turn is None or turn.fallback is None or not turn.fallback.retryable:
                raise ValueError("retry requires a server-marked retryable fallback")
        self._state = StorefrontShellState(
            current_turn=self._state.current_turn,
            submitting=self._state.submitting,
            pending_action=StorefrontActionRequest(action=action),
        )
