import pytest

from storefront import (
    MinimalStorefrontShell,
    StorefrontUserAction,
    build_storefront_turn_view,
)
from tests.unit.test_s07_t01_storefront_view_model import (
    _answer_envelope,
    _fallback_envelope,
)

pytestmark = pytest.mark.unit


def test_submit_clears_prior_turn_while_loading_and_accepts_server_view() -> None:
    shell = MinimalStorefrontShell()
    shell.accept_server_turn(build_storefront_turn_view(_answer_envelope()))

    shell.begin_submit()

    assert shell.state.submitting is True
    assert shell.state.current_turn is None
    shell.accept_server_turn(build_storefront_turn_view(_answer_envelope()))
    assert shell.state.submitting is False
    assert shell.state.current_turn is not None


def test_server_confirmed_view_keeps_target_constraints_and_clarification_visible() -> (
    None
):
    shell = MinimalStorefrontShell()
    view = build_storefront_turn_view(_answer_envelope())

    shell.accept_server_turn(view)

    assert shell.state.current_turn == view
    assert shell.state.current_turn.target == view.target
    assert shell.state.current_turn.constraint_state == view.constraint_state


def test_only_user_action_can_queue_retry_and_server_must_mark_it_retryable() -> None:
    shell = MinimalStorefrontShell()
    shell.accept_server_turn(build_storefront_turn_view(_fallback_envelope()))

    with pytest.raises(ValueError, match="server-marked retryable"):
        shell.request_user_action(StorefrontUserAction.RETRY)

    shell.request_user_action(StorefrontUserAction.CLARIFY)
    assert shell.state.pending_action is not None
    assert shell.state.pending_action.action is StorefrontUserAction.CLARIFY
