"""T08 transport-level Slice 1 journeys through the typed minimal client."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import backend.application.slice_1 as slice_1_module
from backend.api import MinimalConversationClient, create_conversation_api
from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    TURN_REQUEST_VALIDATION_HTTP_STATUS,
    AnswerEnvelope,
    AnswerPayload,
    AttributeStatus,
    AttributeValue,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    InternalDiagnosticCode,
    PageContext,
    ProductCard,
    ToolResult,
    ToolStatus,
    TraceOperation,
    TurnRequest,
)
from backend.shopify import (
    DeterministicShopifyFixture,
    FixtureOutcome,
)

pytestmark = pytest.mark.e2e

NOW = datetime(2026, 8, 30, 14, 20, tzinfo=UTC)
CORRELATION_ID = "correlation-t08-e2e"


def _turn(
    question: str,
    *,
    product_id: str = "drone-mini",
    variant_id: str | None = "mini-standard",
) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t08-e2e",
            message_id="message-t08-e2e",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(product_id=product_id, variant_id=variant_id),
    )


def _system(
    *,
    outcome: FixtureOutcome | None = None,
) -> tuple[
    MinimalConversationClient,
    DeterministicShopifyFixture,
    InMemoryTraceSink,
]:
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
    transport = TestClient(create_conversation_api(service))
    return MinimalConversationClient(transport), fixture, sink


@pytest.mark.parametrize(
    ("turn", "outcome", "reason", "expected_field"),
    [
        (
            _turn("这个套装有几块电池？"),
            EnvelopeOutcome.ANSWER,
            None,
            "battery_count",
        ),
        (
            _turn("这款无人机的制造商是谁？", variant_id=None),
            EnvelopeOutcome.ANSWER,
            None,
            "manufacturer",
        ),
        (
            _turn("这个套装有几块电池？", variant_id=None),
            EnvelopeOutcome.FALLBACK,
            FallbackReasonCode.VARIANT_REQUIRED,
            None,
        ),
        (
            _turn(
                "这款无人机的制造商是谁？",
                product_id="missing-product",
                variant_id=None,
            ),
            EnvelopeOutcome.FALLBACK,
            FallbackReasonCode.PRODUCT_NOT_FOUND,
            None,
        ),
        (
            _turn("这个套装有几块电池？", variant_id="missing-variant"),
            EnvelopeOutcome.FALLBACK,
            FallbackReasonCode.VARIANT_NOT_FOUND,
            None,
        ),
        (
            _turn(
                "这个套装有几块电池？",
                product_id="drone-mini",
                variant_id="cine-standard",
            ),
            EnvelopeOutcome.FALLBACK,
            FallbackReasonCode.VARIANT_NOT_FOUND,
            None,
        ),
        (
            _turn("这个套装支持避障吗？"),
            EnvelopeOutcome.FALLBACK,
            FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
            None,
        ),
        (
            _turn("请推荐一款适合旅行的无人机。", variant_id=None),
            EnvelopeOutcome.FALLBACK,
            FallbackReasonCode.OUT_OF_SCOPE,
            None,
        ),
    ],
    ids=[
        "explicit-variant-happy-path",
        "product-shared",
        "variant-required",
        "product-not-found",
        "variant-not-found",
        "foreign-variant-not-found",
        "unknown-fact",
        "out-of-scope",
    ],
)
def test_minimal_client_runs_required_answer_and_fallback_journeys(
    turn: TurnRequest,
    outcome: EnvelopeOutcome,
    reason: FallbackReasonCode | None,
    expected_field: str | None,
) -> None:
    client, fixture, sink = _system()

    envelope = client.ask(turn)
    payload = AnswerEnvelope.model_validate_json(envelope.to_wire_json()).root

    assert payload.outcome is outcome
    assert payload.product_card is None
    assert payload.trace_correlation_id == CORRELATION_ID
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
    if expected_field is not None:
        assert payload.claims[0].field == expected_field
    if reason is not None:
        assert payload.fallback.reason_code is reason
        assert payload.claims == payload.evidence == payload.bindings == []
    assert fixture.write_call_count == 0


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
def test_minimal_client_preserves_tool_failure_without_fact_claims(
    question: str,
    outcome: FixtureOutcome,
    reason: FallbackReasonCode,
    retryable: bool,
    actions: list[str],
) -> None:
    client, fixture, sink = _system(outcome=outcome)

    payload = client.ask(_turn(question)).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is reason
    assert payload.fallback.retryable is retryable
    assert payload.fallback.next_actions == actions
    assert payload.claims == payload.evidence == payload.bindings == []
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
    assert fixture.write_call_count == 0


def test_matching_product_card_survives_client_api_and_integrity_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_compose: Callable[[AnswerPayload], AnswerEnvelope] = (
        slice_1_module._compose_answer
    )

    def inject_matching_card(payload: AnswerPayload) -> AnswerEnvelope:
        card = ProductCard(
            store_id=payload.resolved_scope.store_id,
            product_id=payload.resolved_scope.product_id,
            variant_id=payload.resolved_scope.variant_id,
            display_title="Aero Mini",
        )
        return original_compose(payload.model_copy(update={"product_card": card}))

    monkeypatch.setattr(slice_1_module, "_compose_answer", inject_matching_card)
    client, fixture, sink = _system()

    payload = client.ask(_turn("这个套装有几块电池？")).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.product_card is not None
    assert (
        payload.product_card.store_id,
        payload.product_card.product_id,
        payload.product_card.variant_id,
    ) == (
        payload.resolved_scope.store_id,
        payload.resolved_scope.product_id,
        payload.resolved_scope.variant_id,
    )
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
    assert fixture.write_call_count == 0


@pytest.mark.parametrize(
    ("corruption", "diagnostic"),
    [
        ("evidence-product", InternalDiagnosticCode.EVIDENCE_SCOPE_MISMATCH),
        ("evidence-variant", InternalDiagnosticCode.EVIDENCE_SCOPE_MISMATCH),
        ("product-card", InternalDiagnosticCode.OUTPUT_SCOPE_MISMATCH),
    ],
    ids=["matrix-11-product", "matrix-12-variant", "matrix-13-card"],
)
def test_scope_mismatch_fails_closed_across_client_and_api(
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
    diagnostic: InternalDiagnosticCode,
) -> None:
    original_compose: Callable[[AnswerPayload], AnswerEnvelope] = (
        slice_1_module._compose_answer
    )

    def inject_scope_corruption(payload: AnswerPayload) -> AnswerEnvelope:
        if corruption == "evidence-product":
            wrong_evidence = payload.evidence[0].model_copy(
                update={"product_id": "drone-cine"}
            )
            payload = payload.model_copy(update={"evidence": [wrong_evidence]})
        elif corruption == "evidence-variant":
            wrong_evidence = payload.evidence[0].model_copy(
                update={"variant_id": "mini-explorer"}
            )
            payload = payload.model_copy(update={"evidence": [wrong_evidence]})
        else:
            wrong_card = ProductCard(
                store_id=payload.resolved_scope.store_id,
                product_id=payload.resolved_scope.product_id,
                variant_id="mini-explorer",
                display_title="Wrong Variant",
            )
            payload = payload.model_copy(update={"product_card": wrong_card})
        return original_compose(payload)

    monkeypatch.setattr(
        slice_1_module,
        "_compose_answer",
        inject_scope_corruption,
    )
    client, fixture, sink = _system()

    payload = client.ask(_turn("这个套装有几块电池？")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is (
        FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR
    )
    assert diagnostic.value not in payload.to_wire_json()
    assert {
        event.summary.diagnostic_code
        for event in sink.events
        if event.summary.diagnostic_code is not None
    } == {diagnostic}
    assert fixture.write_call_count == 0


class _MissingObservedAtPort:
    def get_products(self, *, store_id: str, product_id: str):
        raise AssertionError("Dynamic Matrix #14 must not read products")

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ):
        raise AssertionError("Dynamic Matrix #14 must not read variants")

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ):
        fact = AttributeValue(
            status=AttributeStatus.KNOWN,
            value=2999,
            unit="CNY",
            source_ref="controlled://commerce#price",
        )
        return ToolResult.model_construct(
            status=ToolStatus.SUCCESS,
            data={"price": fact},
            source="controlled://commerce",
            observed_at=None,
            retryable=False,
            error_code=None,
            missing_fields=[],
        )


def test_missing_dynamic_freshness_maps_internal_diagnostic_across_transport() -> None:
    sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=_MissingObservedAtPort(),
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: NOW,
    )
    client = MinimalConversationClient(TestClient(create_conversation_api(service)))

    payload = client.ask(_turn("这款现在多少钱？")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is (
        FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR
    )
    assert payload.fallback.retryable is False
    assert payload.claims == payload.evidence == payload.bindings == []
    assert "DYNAMIC_FACT_FRESHNESS_MISSING" not in payload.to_wire_json()
    assert {
        event.summary.diagnostic_code
        for event in sink.events
        if event.summary.diagnostic_code is not None
    } == {InternalDiagnosticCode.DYNAMIC_FACT_FRESHNESS_MISSING}


class _CountingInterpreter:
    def __init__(self) -> None:
        self.calls = 0
        self._delegate = DeterministicQuestionInterpreter()

    def interpret(self, request: TurnRequest):
        self.calls += 1
        return self._delegate.interpret(request)


class _CountingApplication:
    def __init__(self, delegate: Slice1ApplicationService) -> None:
        self.calls = 0
        self._delegate = delegate

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        self.calls += 1
        return self._delegate.answer(request)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda body: body.pop("user_text"),
        lambda body: body.update(schema_version="2.0"),
        lambda body: body.update(page_context=[]),
    ],
    ids=["missing-field", "invalid-version", "invalid-page-context-type"],
)
def test_invalid_wire_input_stops_before_every_downstream_boundary(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    fixture = DeterministicShopifyFixture(clock=lambda: NOW)
    interpreter = _CountingInterpreter()
    sink = InMemoryTraceSink()
    service = Slice1ApplicationService(
        shopify=fixture,
        interpreter=interpreter,
        trace_sink=sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: NOW,
    )
    application = _CountingApplication(service)
    transport = TestClient(create_conversation_api(application))
    invalid_body = _turn("这个套装有几块电池？").to_wire()
    mutate(invalid_body)

    response = transport.post("/v1/conversation/turn", json=invalid_body)

    assert response.status_code == TURN_REQUEST_VALIDATION_HTTP_STATUS
    assert response.json() == {
        "schema_version": SCHEMA_VERSION,
        "error_code": "INVALID_TURN_REQUEST",
        "message": "Request validation failed.",
    }
    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(response.json())
    assert application.calls == 0
    assert interpreter.calls == 0
    assert fixture.call_ledger == ()
    assert fixture.write_call_count == 0
    assert sink.events == ()
