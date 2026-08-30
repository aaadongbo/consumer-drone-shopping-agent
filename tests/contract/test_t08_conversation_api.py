"""T08 contract gates for the thin Conversation API and typed client."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api import MinimalConversationClient, create_conversation_api
from backend.common import (
    SCHEMA_VERSION,
    TURN_REQUEST_VALIDATION_HTTP_STATUS,
    AnswerEnvelope,
    ConversationRef,
    EnvelopeOutcome,
    FallbackPayload,
    FallbackReasonCode,
    ObjectScope,
    PageContext,
    StandardFallback,
    TurnRequest,
    TurnRequestValidationResponse,
)

pytestmark = pytest.mark.contract

NOW = datetime(2026, 8, 30, 14, 0, tzinfo=UTC)


def _turn() -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t08-contract",
            message_id="message-t08-contract",
        ),
        user_text="请推荐一款适合旅行的无人机。",
        locale="zh-CN",
        page_context=PageContext(product_id="drone-mini"),
    )


class _RecordingApplication:
    def __init__(self) -> None:
        self.requests: list[TurnRequest] = []

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        self.requests.append(request)
        scope = ObjectScope(
            store_id=request.store_id,
            product_id=request.page_context.product_id,
            variant_id=request.page_context.variant_id,
        )
        message = "该请求不属于当前商品事实查询范围。"
        return AnswerEnvelope(
            root=FallbackPayload(
                schema_version=SCHEMA_VERSION,
                outcome=EnvelopeOutcome.FALLBACK,
                conversation=request.conversation,
                trace_correlation_id="correlation-t08-contract",
                resolved_scope=scope,
                text=message,
                fallback=StandardFallback(
                    reason_code=FallbackReasonCode.OUT_OF_SCOPE,
                    message=message,
                    retryable=False,
                    next_actions=["改问当前商品的规格"],
                    resolved_scope=scope,
                ),
            )
        )


def test_valid_wire_request_is_delegated_as_the_public_turn_contract() -> None:
    application = _RecordingApplication()
    transport = TestClient(create_conversation_api(application))

    response = transport.post("/v1/conversation/turn", json=_turn().to_wire())
    envelope = AnswerEnvelope.model_validate(response.json())

    assert response.status_code == 200
    assert application.requests == [_turn()]
    assert envelope.root.outcome is EnvelopeOutcome.FALLBACK
    assert envelope.root.fallback.reason_code is FallbackReasonCode.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "invalid_body",
    [
        {
            "schema_version": SCHEMA_VERSION,
            "store_id": "store-drone-cn",
            "conversation": {
                "conversation_id": "conversation-t08-contract",
                "message_id": "message-t08-contract",
            },
            "locale": "zh-CN",
            "page_context": {"product_id": "drone-mini"},
        },
        {**_turn().to_wire(), "schema_version": "2.0"},
        {**_turn().to_wire(), "conversation": "not-an-object"},
    ],
    ids=["missing-user-text", "unknown-version", "invalid-conversation-type"],
)
def test_invalid_wire_request_returns_only_the_safe_transport_contract(
    invalid_body: dict[str, object],
) -> None:
    application = _RecordingApplication()
    transport = TestClient(create_conversation_api(application))

    response = transport.post("/v1/conversation/turn", json=invalid_body)
    rejection = TurnRequestValidationResponse.model_validate(response.json())

    assert response.status_code == TURN_REQUEST_VALIDATION_HTTP_STATUS
    assert rejection.to_wire() == {
        "schema_version": SCHEMA_VERSION,
        "error_code": "INVALID_TURN_REQUEST",
        "message": "Request validation failed.",
    }
    assert application.requests == []
    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(response.json())


def test_minimal_client_uses_public_request_and_response_models_end_to_end() -> None:
    application = _RecordingApplication()
    transport = TestClient(create_conversation_api(application))
    client = MinimalConversationClient(transport)

    envelope = client.ask(_turn())
    reparsed = AnswerEnvelope.model_validate_json(envelope.to_wire_json())

    assert application.requests == [_turn()]
    assert reparsed == envelope
