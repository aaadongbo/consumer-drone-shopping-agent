"""T06 public Envelope contract checks for every newly generated fallback."""

from datetime import UTC, datetime

import pytest

from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    PageContext,
    TraceOperation,
    TurnRequest,
)
from backend.shopify.fixture import (
    DeterministicShopifyFixture,
    FixtureOutcome,
)

pytestmark = pytest.mark.contract

NOW = datetime(2026, 8, 30, 12, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    ("question", "outcome", "reason"),
    [
        (
            "这个套装支持避障吗？",
            None,
            FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
        ),
        (
            "这个套装有几块电池？",
            FixtureOutcome.TIMEOUT,
            FallbackReasonCode.TOOL_TIMEOUT,
        ),
        (
            "这个套装有几块电池？",
            FixtureOutcome.RATE_LIMITED,
            FallbackReasonCode.TOOL_RATE_LIMITED,
        ),
        (
            "这个套装有几块电池？",
            FixtureOutcome.UNAUTHORIZED,
            FallbackReasonCode.TOOL_UNAUTHORIZED,
        ),
        (
            "这个套装配遥控器吗？",
            FixtureOutcome.PARTIAL,
            FallbackReasonCode.TOOL_PARTIAL_RESULT,
        ),
        (
            "请推荐一款适合旅行的无人机。",
            None,
            FallbackReasonCode.OUT_OF_SCOPE,
        ),
    ],
)
def test_runtime_fallback_round_trips_through_public_envelope(
    question: str,
    outcome: FixtureOutcome | None,
    reason: FallbackReasonCode,
) -> None:
    forced_outcomes = (
        {TraceOperation.GET_VARIANTS: outcome} if outcome is not None else None
    )
    fixture = DeterministicShopifyFixture(
        clock=lambda: NOW,
        forced_outcomes=forced_outcomes,
    )
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "correlation-t06-contract",
        clock=lambda: NOW,
    )
    request = TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t06-contract",
            message_id="message-t06-contract",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(
            product_id="drone-mini",
            variant_id="mini-standard",
        ),
    )

    envelope = service.answer(request)
    parsed = AnswerEnvelope.model_validate_json(envelope.to_wire_json())

    assert parsed == envelope
    assert parsed.root.outcome is EnvelopeOutcome.FALLBACK
    assert parsed.root.fallback.reason_code is reason
    assert parsed.root.fallback.message == parsed.root.text
    assert parsed.root.fallback.next_actions
    assert parsed.root.fallback.resolved_scope == parsed.root.resolved_scope
