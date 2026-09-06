"""S11-T05 integration checks for the embeddable storefront widget."""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.api import create_conversation_api
from backend.api.guardrails import install_cors_guardrail
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
from storefront import StorefrontWidget, WidgetEmbedConfig, WidgetStatus

pytestmark = pytest.mark.integration


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
        return AnswerEnvelope(
            root=AnswerPayload(
                schema_version=SCHEMA_VERSION,
                outcome=EnvelopeOutcome.ANSWER,
                conversation=request.conversation,
                trace_correlation_id="correlation-widget",
                resolved_scope=scope,
                text="Server-confirmed answer.",
                product_card=ProductCard(
                    store_id=scope.store_id,
                    product_id=scope.product_id,
                    variant_id=scope.variant_id,
                    display_title="DJI Mini Standard",
                ),
            )
        )


class _RetryApplication:
    def __init__(self) -> None:
        self.calls = 0

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        self.calls += 1
        scope = ObjectScope(
            store_id=request.store_id,
            product_id=request.page_context.product_id,
            variant_id=request.page_context.variant_id,
        )
        if self.calls == 1:
            message = "Temporary beta path timeout."
            return AnswerEnvelope(
                root=FallbackPayload(
                    schema_version=SCHEMA_VERSION,
                    outcome=EnvelopeOutcome.FALLBACK,
                    conversation=request.conversation,
                    trace_correlation_id="correlation-widget-fallback",
                    resolved_scope=scope,
                    text=message,
                    fallback=StandardFallback(
                        reason_code=FallbackReasonCode.TOOL_TIMEOUT,
                        message=message,
                        retryable=True,
                        next_actions=["Retry"],
                        resolved_scope=scope,
                    ),
                )
            )
        return AnswerEnvelope(
            root=AnswerPayload(
                schema_version=SCHEMA_VERSION,
                outcome=EnvelopeOutcome.ANSWER,
                conversation=request.conversation,
                trace_correlation_id="correlation-widget-retry",
                resolved_scope=scope,
                text="Retry succeeded.",
                product_card=ProductCard(
                    store_id=scope.store_id,
                    product_id=scope.product_id,
                    variant_id=scope.variant_id,
                    display_title="DJI Mini Standard",
                ),
            )
        )


class _MismatchedCardApplication:
    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        scope = ObjectScope(
            store_id=request.store_id,
            product_id=request.page_context.product_id,
            variant_id=request.page_context.variant_id,
        )
        return AnswerEnvelope(
            root=AnswerPayload(
                schema_version=SCHEMA_VERSION,
                outcome=EnvelopeOutcome.ANSWER,
                conversation=request.conversation,
                trace_correlation_id="correlation-widget-mismatch",
                resolved_scope=scope,
                text="Server returned mismatched display data.",
                product_card=ProductCard(
                    store_id=scope.store_id,
                    product_id="wrong-product",
                    variant_id=scope.variant_id,
                    display_title="Wrong Product",
                ),
            )
        )


class _ExplodingTransport:
    def post(self, url: str, *, json: dict[str, object]) -> object:
        raise RuntimeError(f"secret-token leaked through {url}: {json}")


class _ValidationResponse:
    status_code = 422

    def json(self) -> dict[str, str]:
        return {
            "schema_version": SCHEMA_VERSION,
            "error_code": "INVALID_TURN_REQUEST",
            "message": "Request validation failed.",
        }


class _RejectingTransport:
    def post(self, url: str, *, json: dict[str, object]) -> _ValidationResponse:
        return _ValidationResponse()


def _config() -> WidgetEmbedConfig:
    return WidgetEmbedConfig(
        current_origin="https://beta-store.example",
        allowed_origins=("https://beta-store.example",),
        store_id="store-drone-cn",
        product_id="drone-mini",
        variant_id="mini-standard",
    )


def _cors_api(application: object, origins: tuple[str, ...]) -> FastAPI:
    api = create_conversation_api(application)
    install_cors_guardrail(api, origins)
    return api


def test_widget_posts_only_conversation_turn_with_current_page_context() -> None:
    application = _RecordingApplication()
    widget = StorefrontWidget(
        config=_config(),
        transport=TestClient(_cors_api(application, ("https://beta-store.example",))),
        conversation_id="conversation-widget",
        message_id_factory=lambda sequence: f"message-{sequence}",
    )

    loading = widget.begin_submit("Is this the standard combo?")
    final = widget.submit("Is this the standard combo?")

    assert loading.status is WidgetStatus.LOADING
    assert final.status is WidgetStatus.ANSWER
    assert final.target is not None
    assert final.target.title == "DJI Mini Standard"
    assert len(application.requests) == 1
    request = application.requests[0]
    assert request.conversation == ConversationRef(
        conversation_id="conversation-widget",
        message_id="message-1",
    )
    assert request.store_id == "store-drone-cn"
    assert request.page_context == PageContext(
        product_id="drone-mini",
        variant_id="mini-standard",
    )
    assert request.user_text == "Is this the standard combo?"


def test_widget_retry_and_reset_stay_inside_local_ui_state() -> None:
    application = _RetryApplication()
    widget = StorefrontWidget(
        config=_config(),
        transport=TestClient(create_conversation_api(application)),
        conversation_id="conversation-widget",
    )

    fallback = widget.submit("What is the current price?")
    retried = widget.retry()
    reset = widget.reset()

    assert fallback.status is WidgetStatus.FALLBACK
    assert fallback.retryable is True
    assert retried.status is WidgetStatus.ANSWER
    assert retried.message == "Retry succeeded."
    assert reset.status is WidgetStatus.IDLE
    assert application.calls == 2


def test_transport_rejection_and_unexpected_error_are_safe_widget_states() -> None:
    widget = StorefrontWidget(
        config=_config(),
        transport=_RejectingTransport(),
        conversation_id="conversation-widget",
    )
    rejection = widget.submit("hello")

    assert rejection.status is WidgetStatus.TRANSPORT_REJECTION
    assert rejection.rejection is not None
    assert rejection.rejection.status_code == 422

    broken = StorefrontWidget(
        config=_config(),
        transport=_ExplodingTransport(),
        conversation_id="conversation-widget",
    ).submit("hello")

    assert broken.status is WidgetStatus.ERROR
    assert (
        broken.message == "The storefront assistant is unavailable. Please try again."
    )
    assert "secret-token" not in broken.model_dump_json()


def test_response_mapping_errors_are_safe_widget_states() -> None:
    broken = StorefrontWidget(
        config=_config(),
        transport=TestClient(create_conversation_api(_MismatchedCardApplication())),
        conversation_id="conversation-widget",
    ).submit("hello")

    assert broken.status is WidgetStatus.ERROR
    assert (
        broken.message == "The storefront assistant is unavailable. Please try again."
    )
    assert "wrong-product" not in broken.model_dump_json()


def test_cors_accepts_only_the_explicit_widget_origin() -> None:
    application = _RecordingApplication()
    client = TestClient(_cors_api(application, ("https://beta-store.example",)))

    approved = client.options(
        "/v1/conversation/turn",
        headers={
            "Origin": "https://beta-store.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    rejected = client.options(
        "/v1/conversation/turn",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert approved.status_code == 200
    assert (
        approved.headers["access-control-allow-origin"] == "https://beta-store.example"
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_widget_cannot_be_mounted_with_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="explicit CORS origins"):
        _cors_api(_RecordingApplication(), ("*",))

    api = FastAPI()
    api.add_middleware(CORSMiddleware, allow_origins=["*"])
    assert any(
        middleware.cls is CORSMiddleware
        and middleware.kwargs.get("allow_origins") == ["*"]
        for middleware in api.user_middleware
    )
