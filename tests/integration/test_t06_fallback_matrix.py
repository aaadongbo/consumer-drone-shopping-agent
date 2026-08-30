"""T06 application-boundary Matrix #6 through #10 and #15."""

from collections import Counter
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
    TraceEventType,
    TraceOperation,
    TurnRequest,
)
from backend.shopify.fixture import (
    DeterministicShopifyFixture,
    FixtureOutcome,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 30, 12, 30, tzinfo=UTC)
CORRELATION_ID = "correlation-t06-matrix"


def _request(question: str, *, variant_id: str | None = "mini-standard") -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t06-matrix",
            message_id="message-t06-matrix",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(
            product_id="drone-mini",
            variant_id=variant_id,
        ),
    )


def _system(
    outcome: FixtureOutcome | None = None,
) -> tuple[Slice1ApplicationService, DeterministicShopifyFixture, InMemoryTraceSink]:
    forced_outcomes = (
        {TraceOperation.GET_VARIANTS: outcome} if outcome is not None else None
    )
    fixture = DeterministicShopifyFixture(
        clock=lambda: NOW,
        forced_outcomes=forced_outcomes,
    )
    sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: NOW,
    )
    return service, fixture, sink


def test_matrix_6_unknown_fact_returns_non_assertive_fallback() -> None:
    service, fixture, sink = _system()

    envelope = service.answer(_request("这个套装支持避障吗？"))
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root
    copy = f"{payload.text} {' '.join(payload.fallback.next_actions)}".casefold()

    _assert_fallback(
        payload,
        FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
        retryable=False,
        actions=["查看其他已知规格", "联系商家确认"],
    )
    assert all(term not in copy for term in ("不支持", "false", " 0 "))
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.SHOPIFY_READ_CALLED,
        TraceEventType.TOOL_RESULT,
        TraceEventType.PAGE_CONTEXT_RESOLVED,
        TraceEventType.FALLBACK_PRODUCED,
    ]
    _assert_only_variant_read(fixture)
    _assert_correlated(sink)


def test_known_obstacle_sensing_uses_its_own_answer_semantics() -> None:
    service, fixture, sink = _system()

    envelope = service.answer(
        _request("这个套装支持避障吗？", variant_id="mini-explorer")
    )
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.text == "这个套装的避障规格为 three-direction。"
    assert "电池" not in payload.text
    assert payload.claims[0].field == "obstacle_sensing"
    assert payload.claims[0].fact.value == "three-direction"
    assert payload.evidence[0].fact == payload.claims[0].fact
    assert payload.resolved_scope.variant_id == "mini-explorer"
    assert payload.evidence[0].variant_id == "mini-explorer"
    _assert_only_variant_read(fixture)
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}


@pytest.mark.parametrize(
    ("question", "outcome", "reason", "retryable", "actions"),
    [
        (
            "这个套装有几块电池？",
            FixtureOutcome.TIMEOUT,
            FallbackReasonCode.TOOL_TIMEOUT,
            True,
            ["重试"],
        ),
        (
            "这个套装有几块电池？",
            FixtureOutcome.RATE_LIMITED,
            FallbackReasonCode.TOOL_RATE_LIMITED,
            True,
            ["稍后重试"],
        ),
        (
            "这个套装有几块电池？",
            FixtureOutcome.UNAUTHORIZED,
            FallbackReasonCode.TOOL_UNAUTHORIZED,
            False,
            ["联系支持或检查商店连接"],
        ),
        (
            "这个套装配遥控器吗？",
            FixtureOutcome.PARTIAL,
            FallbackReasonCode.TOOL_PARTIAL_RESULT,
            True,
            ["重试", "询问其他可确认字段"],
        ),
    ],
    ids=[
        "matrix-7-timeout",
        "matrix-8-rate-limit",
        "matrix-9-auth",
        "matrix-10-partial",
    ],
)
def test_matrix_7_through_10_tool_failures_never_reuse_partial_or_old_facts(
    question: str,
    outcome: FixtureOutcome,
    reason: FallbackReasonCode,
    retryable: bool,
    actions: list[str],
) -> None:
    service, fixture, sink = _system(outcome)

    envelope = service.answer(_request(question))
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    _assert_fallback(payload, reason, retryable=retryable, actions=actions)
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.SHOPIFY_READ_CALLED,
        TraceEventType.TOOL_RESULT,
        TraceEventType.FALLBACK_PRODUCED,
    ]
    _assert_only_variant_read(fixture)
    _assert_correlated(sink)


def test_matrix_15_out_of_scope_returns_without_shopify_call() -> None:
    service, fixture, sink = _system()

    envelope = service.answer(_request("请推荐一款适合旅行的无人机。", variant_id=None))
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    _assert_fallback(
        payload,
        FallbackReasonCode.OUT_OF_SCOPE,
        retryable=False,
        actions=["改问当前商品的规格", "联系人工渠道"],
    )
    assert fixture.call_ledger == ()
    assert fixture.write_call_count == 0
    assert [event.event_type for event in sink.events] == [
        TraceEventType.TURN_REQUEST_ACCEPTED,
        TraceEventType.ROUTE_DECISION,
        TraceEventType.FALLBACK_PRODUCED,
    ]
    _assert_correlated(sink)


def _assert_fallback(
    payload,
    reason: FallbackReasonCode,
    *,
    retryable: bool,
    actions: list[str],
) -> None:
    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.product_card is None
    assert payload.claims == []
    assert payload.evidence == []
    assert payload.bindings == []
    assert payload.freshness is None
    assert payload.fallback.reason_code is reason
    assert payload.fallback.retryable is retryable
    assert payload.fallback.next_actions == actions
    assert payload.fallback.message == payload.text
    assert payload.trace_correlation_id == CORRELATION_ID


def _assert_only_variant_read(fixture: DeterministicShopifyFixture) -> None:
    counts = Counter(entry.operation for entry in fixture.call_ledger)
    assert counts == Counter({TraceOperation.GET_VARIANTS: 1})
    assert fixture.write_call_count == 0


def _assert_correlated(sink: InMemoryTraceSink) -> None:
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
    assert TraceEventType.EVIDENCE_ACCEPTED not in {
        event.event_type for event in sink.events
    }
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }
