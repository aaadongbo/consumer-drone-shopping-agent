"""S07-T04 replay harness across existing API, client and storefront adapters."""

import pytest
from fastapi.testclient import TestClient

from backend.api import MinimalConversationClient, create_conversation_api
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    AnswerPayload,
    ConversationRef,
    EnvelopeOutcome,
    FallbackPayload,
    FallbackReasonCode,
    ObjectScope,
    PageContext,
    ProductCard,
    StandardFallback,
    TurnRequest,
)
from backend.common.contracts import ConversationStateProjection
from storefront import MinimalStorefrontShell, build_storefront_turn_view

pytestmark = pytest.mark.integration


class _ServerAuthoritativeReplayApplication:
    """Deterministic harness state used only to exercise the existing transport."""

    def __init__(self) -> None:
        self.calls = 0
        self._constraints: list[dict[str, object]] = []
        self._pending_clarification: dict[str, object] | None = None
        self._pending_switch: dict[str, object] | None = None
        self._revision = 0

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        self.calls += 1
        action = request.user_text
        if action == "add":
            self._constraints = [_constraint(5000)]
        elif action == "modify":
            self._constraints = [_constraint(4000)]
        elif action == "withdraw":
            self._constraints = []
        elif action == "skip":
            self._pending_clarification = None
        elif action in {"clarify-1", "clarify-2"}:
            count = int(action[-1])
            self._pending_clarification = {
                "prompt": "请说明预算。",
                "source_message_id": request.conversation.message_id,
                "consecutive_count": count,
            }
        elif action == "switch":
            self._pending_switch = {
                "schema_version": SCHEMA_VERSION,
                "target": {
                    "store_id": request.store_id,
                    "product_id": "drone-cine",
                },
                "created_by_message_id": request.conversation.message_id,
                "created_at_revision": self._revision + 1,
                "expected_revision": self._revision + 1,
                "trigger": "USER_SWITCH_REQUEST",
                "expires_after_turns": 1,
            }
        elif action != "fallback":
            raise AssertionError(f"unexpected replay action: {action}")
        self._revision += 1
        scope = ObjectScope(store_id=request.store_id, product_id="drone-mini")
        state = ConversationStateProjection(
            active_constraints=tuple(self._constraints),
            pending_clarification=self._pending_clarification,
            pending_switch=self._pending_switch,
            revision=self._revision,
        )
        if action == "fallback":
            message = "当前没有可确认的结果。"
            return AnswerEnvelope(
                root=FallbackPayload(
                    schema_version=SCHEMA_VERSION,
                    outcome=EnvelopeOutcome.FALLBACK,
                    conversation=request.conversation,
                    trace_correlation_id=f"correlation-{self._revision}",
                    resolved_scope=scope,
                    text=message,
                    fallback=StandardFallback(
                        reason_code=FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
                        message=message,
                        retryable=False,
                        next_actions=["补充预算"],
                        resolved_scope=scope,
                    ),
                    conversation_state=state,
                )
            )
        return AnswerEnvelope(
            root=AnswerPayload(
                schema_version=SCHEMA_VERSION,
                outcome=EnvelopeOutcome.ANSWER,
                conversation=request.conversation,
                trace_correlation_id=f"correlation-{self._revision}",
                resolved_scope=scope,
                text="服务器已确认状态。",
                product_card=ProductCard(
                    store_id=scope.store_id,
                    product_id=scope.product_id,
                    display_title="Aero Mini",
                ),
                conversation_state=state,
            )
        )


def _constraint(value: int) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_turn_id": "server",
        "field": "price",
        "operator": "LTE",
        "value": value,
        "unit": "CNY",
        "hardness": "HARD",
        "confidence": 1.0,
        "provenance": "DETERMINISTIC_RULE",
        "status": "ACTIVE",
    }


def _turn(action: str, sequence: int) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-s07",
        conversation=ConversationRef(
            conversation_id="conversation-s07", message_id=f"message-{sequence}"
        ),
        user_text=action,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-mini"),
    )


def test_storefront_replays_server_confirmed_state_over_multiple_turns() -> None:
    application = _ServerAuthoritativeReplayApplication()
    client = MinimalConversationClient(TestClient(create_conversation_api(application)))
    shell = MinimalStorefrontShell()
    observed = []

    for sequence, action in enumerate(
        (
            "add",
            "modify",
            "switch",
            "withdraw",
            "clarify-1",
            "clarify-2",
            "skip",
            "fallback",
        ),
        start=1,
    ):
        shell.begin_submit()
        view = build_storefront_turn_view(client.ask(_turn(action, sequence)))
        shell.accept_server_turn(view)
        observed.append(view)

    assert application.calls == 8
    assert [view.constraint_state.revision for view in observed] == list(range(1, 9))
    assert observed[0].constraint_state.active_constraints[0].value == 5000
    assert observed[1].constraint_state.active_constraints[0].value == 4000
    assert (
        observed[2].constraint_state.pending_target_switch.target.product_id
        == "drone-cine"
    )
    assert observed[3].constraint_state.active_constraints == ()
    assert observed[5].constraint_state.pending_clarification.consecutive_count == 2
    assert observed[6].constraint_state.pending_clarification is None
    assert shell.state.current_turn == observed[-1]
    assert observed[-1].target.scope == observed[-1].fallback.resolved_scope
    assert observed[-1].trace_correlation_id == "correlation-8"
