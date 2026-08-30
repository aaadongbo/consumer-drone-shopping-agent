"""T07 contract gates for public consistency fallbacks and dynamic answers."""

from datetime import UTC, datetime

import pytest

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

pytestmark = pytest.mark.contract

NOW = datetime(2026, 8, 30, 13, 30, tzinfo=UTC)


def test_internal_consistency_fallback_is_publicly_valid_without_diagnostic() -> None:
    scope = ObjectScope(
        store_id="store-drone-cn",
        product_id="drone-mini",
        variant_id="mini-standard",
    )
    payload = FallbackPayload(
        schema_version=SCHEMA_VERSION,
        outcome=EnvelopeOutcome.FALLBACK,
        conversation=ConversationRef(
            conversation_id="conversation-t07-contract",
            message_id="message-t07-contract",
        ),
        trace_correlation_id="correlation-t07-contract",
        resolved_scope=scope,
        text="暂时无法可靠确认该商品事实，请停止展示该结论并联系支持。",
        fallback=StandardFallback(
            reason_code=FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR,
            message="暂时无法可靠确认该商品事实，请停止展示该结论并联系支持。",
            retryable=False,
            next_actions=["停止展示该结论", "联系支持"],
            resolved_scope=scope,
        ),
    )

    envelope = AnswerEnvelope(root=payload)
    wire = envelope.to_wire_json()
    restored = AnswerEnvelope.model_validate_json(wire).root

    assert restored.outcome is EnvelopeOutcome.FALLBACK
    assert (
        restored.fallback.reason_code is FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR
    )
    assert "EVIDENCE_SCOPE_MISMATCH" not in wire
    assert "OUTPUT_SCOPE_MISMATCH" not in wire
    assert "DYNAMIC_FACT_FRESHNESS_MISSING" not in wire
    assert NOW.isoformat() not in wire
