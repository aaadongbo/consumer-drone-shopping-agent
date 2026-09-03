"""S07-T01 contract gates for storefront adapter boundaries."""

import pytest
from pydantic import ValidationError

import backend.common as public_contracts
from backend.api import ConversationTransportError
from backend.common import (
    SCHEMA_VERSION,
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
from storefront import RenderStatus, build_storefront_turn_view
from storefront.view_model import validation_rejection_to_view

pytestmark = pytest.mark.contract


def test_storefront_view_models_are_not_exported_as_public_common_contracts() -> None:
    assert "StorefrontTurnView" not in public_contracts.__all__
    assert "ConstraintPresentationState" not in public_contracts.__all__
    assert "FallbackView" not in public_contracts.__all__


def test_existing_public_request_and_response_schema_are_not_extended() -> None:
    turn_schema = TurnRequest.model_json_schema()
    envelope_schema = AnswerEnvelope.model_json_schema()

    assert set(turn_schema["properties"]) == {
        "schema_version",
        "store_id",
        "conversation",
        "user_text",
        "locale",
        "page_context",
    }
    serialized = TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-s07-contract",
            message_id="message-s07-contract",
        ),
        user_text="这个套装有几块电池？",
        locale="zh-CN",
        page_context=PageContext(product_id="drone-mini"),
    ).to_wire()
    assert "storefront" not in serialized
    assert "view" not in serialized
    assert "constraint_state" not in serialized
    assert "storefront" not in str(envelope_schema).casefold()
    assert "constraintpresentationstate" not in str(envelope_schema).casefold()


def test_business_fallback_remains_one_public_answer_envelope() -> None:
    scope = ObjectScope(store_id="store-drone-cn", product_id="drone-mini")
    message = "该请求不属于当前商品事实查询范围。"
    envelope = AnswerEnvelope(
        root=FallbackPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.FALLBACK,
            conversation=ConversationRef(
                conversation_id="conversation-s07-contract",
                message_id="message-s07-contract",
            ),
            trace_correlation_id="correlation-s07-contract",
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

    view = build_storefront_turn_view(envelope)

    assert AnswerEnvelope.model_validate_json(envelope.to_wire_json()) == envelope
    assert view.render_status is RenderStatus.FALLBACK
    assert view.fallback is not None
    assert view.fallback.reason_code is envelope.root.fallback.reason_code
    assert view.fallback.message == envelope.root.fallback.message


def test_transport_422_rejection_is_not_parseable_as_answer_envelope() -> None:
    rejection = TurnRequestValidationResponse(
        schema_version=SCHEMA_VERSION,
        error_code="INVALID_TURN_REQUEST",
        message="Request validation failed.",
    )
    error = ConversationTransportError(status_code=422, response=rejection)

    view = validation_rejection_to_view(rejection)

    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(rejection.to_wire())
    assert view.render_status is RenderStatus.TRANSPORT_REJECTION
    assert view.status_code == error.status_code
