"""S07-T04 contract coverage for the optional replay-state projection."""

import pytest
from pydantic import ValidationError

from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    ConversationRef,
    EnvelopeOutcome,
    FallbackPayload,
    FallbackReasonCode,
    ObjectScope,
    StandardFallback,
)
from backend.common.contracts import ConversationStateProjection

pytestmark = pytest.mark.integration


def _fallback(*, state: ConversationStateProjection | None = None) -> AnswerEnvelope:
    scope = ObjectScope(store_id="store-s07", product_id="drone-mini")
    message = "请补充你的预算。"
    return AnswerEnvelope(
        root=FallbackPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.FALLBACK,
            conversation=ConversationRef(
                conversation_id="conversation-s07", message_id="message-s07"
            ),
            trace_correlation_id="correlation-s07",
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


def test_conversation_state_is_optional_and_wire_backward_compatible() -> None:
    envelope = _fallback()

    assert "conversation_state" not in envelope.to_wire()
    assert AnswerEnvelope.model_validate(envelope.to_wire()) == envelope


def test_conversation_state_is_limited_to_server_replay_fields() -> None:
    state = ConversationStateProjection(
        active_constraints=({"field": "PRICE", "value": 5000},),
        pending_clarification={"prompt": "预算是多少？", "consecutive_count": 1},
        pending_switch=None,
        revision=4,
    )
    wire = _fallback(state=state).to_wire()

    assert wire["conversation_state"] == {
        "active_constraints": [{"field": "PRICE", "value": 5000}],
        "pending_clarification": {"prompt": "预算是多少？", "consecutive_count": 1},
        "revision": 4,
    }
    assert set(ConversationStateProjection.model_json_schema()["properties"]) == {
        "active_constraints",
        "pending_clarification",
        "pending_switch",
        "revision",
    }
    with pytest.raises(ValidationError):
        ConversationStateProjection.model_validate(
            {**state.to_wire(), "owner": "client"}
        )
