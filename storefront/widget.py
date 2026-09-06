"""Embeddable closed-beta storefront widget boundary."""

from collections.abc import Callable
from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from backend.api import (
    CONVERSATION_TURN_PATH,
    ConversationTransportError,
    MinimalConversationClient,
)
from backend.api.conversation import SyncJsonTransport
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    Evidence,
    FreshnessDisclosure,
    ObjectScope,
    PageContext,
    TurnRequest,
)
from backend.common.contracts import WireModel
from storefront.view_model import (
    ConstraintPresentationState,
    FallbackView,
    StorefrontTargetDisplay,
    StorefrontTransportRejection,
    StorefrontTurnView,
    build_storefront_turn_view,
    build_transport_rejection_view,
)

type SchemaVersion = Literal["1.0"]


class WidgetStatus(StrEnum):
    IDLE = "IDLE"
    LOADING = "LOADING"
    ANSWER = "ANSWER"
    FALLBACK = "FALLBACK"
    TRANSPORT_REJECTION = "TRANSPORT_REJECTION"
    ERROR = "ERROR"


class WidgetEmbedConfig(WireModel):
    """Credential-free embed settings for one approved storefront origin."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    current_origin: str
    allowed_origins: tuple[str, ...] = Field(min_length=1)
    backend_endpoint: str = CONVERSATION_TURN_PATH
    store_id: str
    product_id: str
    variant_id: str | None = None
    locale: str = "zh-CN"

    @model_validator(mode="after")
    def validate_closed_beta_embed_boundary(self) -> "WidgetEmbedConfig":
        if self.backend_endpoint != CONVERSATION_TURN_PATH:
            raise ValueError("widget may call only the Conversation API")
        normalized_allowed = tuple(
            _validate_exact_origin(origin) for origin in self.allowed_origins
        )
        current = _validate_exact_origin(self.current_origin)
        if current not in normalized_allowed:
            raise ValueError("current origin must be explicitly allowlisted")
        return self

    @property
    def page_context(self) -> PageContext:
        return PageContext(product_id=self.product_id, variant_id=self.variant_id)

    @property
    def scope(self) -> ObjectScope:
        return ObjectScope(
            store_id=self.store_id,
            product_id=self.product_id,
            variant_id=self.variant_id,
        )


class WidgetEvidenceDisplay(WireModel):
    evidence_id: str
    source: str
    field_locator: str
    scope: ObjectScope
    observed_at: str | None = None


class WidgetRenderState(WireModel):
    """Single render model for loading, final, retry, reset, and safe errors."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    status: WidgetStatus
    target: StorefrontTargetDisplay | None = None
    constraint_state: ConstraintPresentationState | None = None
    message: str | None = None
    evidence: tuple[WidgetEvidenceDisplay, ...] = ()
    freshness: FreshnessDisclosure | None = None
    fallback: FallbackView | None = None
    rejection: StorefrontTransportRejection | None = None
    retryable: bool = False
    can_reset: bool = True

    @model_validator(mode="after")
    def validate_status_shape(self) -> "WidgetRenderState":
        if self.status in {WidgetStatus.ANSWER, WidgetStatus.FALLBACK}:
            if self.target is None or self.constraint_state is None:
                raise ValueError("final widget states require target and constraints")
        if self.status is WidgetStatus.ANSWER and self.message is None:
            raise ValueError("answer widget state requires message")
        if self.status is WidgetStatus.FALLBACK and self.fallback is None:
            raise ValueError("fallback widget state requires fallback")
        if self.status is WidgetStatus.TRANSPORT_REJECTION and self.rejection is None:
            raise ValueError("transport rejection state requires rejection")
        if self.status is WidgetStatus.ERROR and self.message is None:
            raise ValueError("error widget state requires message")
        return self


class StorefrontWidget:
    """Thin embeddable client that delegates all commerce truth to the server."""

    def __init__(
        self,
        *,
        config: WidgetEmbedConfig,
        transport: SyncJsonTransport,
        conversation_id: str,
        message_id_factory: Callable[[int], str] | None = None,
    ) -> None:
        self._config = config
        self._client = MinimalConversationClient(transport)
        self._conversation_id = conversation_id
        self._message_id_factory = message_id_factory or (
            lambda sequence: f"widget-message-{sequence}"
        )
        self._sequence = 0
        self._last_user_text: str | None = None
        self._state = WidgetRenderState(status=WidgetStatus.IDLE)

    @property
    def state(self) -> WidgetRenderState:
        return self._state

    def reset(self) -> WidgetRenderState:
        self._last_user_text = None
        self._state = WidgetRenderState(status=WidgetStatus.IDLE)
        return self._state

    def begin_submit(self, user_text: str) -> WidgetRenderState:
        self._last_user_text = user_text
        self._state = WidgetRenderState(
            status=WidgetStatus.LOADING,
            target=StorefrontTargetDisplay(
                scope=self._config.scope,
                title=_scope_title(self._config.scope),
            ),
            message="Loading",
        )
        return self._state

    def submit(self, user_text: str) -> WidgetRenderState:
        self.begin_submit(user_text)
        request = self._turn_request(user_text)
        try:
            envelope = self._client.ask(request)
        except ConversationTransportError as error:
            self._state = WidgetRenderState(
                status=WidgetStatus.TRANSPORT_REJECTION,
                rejection=build_transport_rejection_view(error),
                retryable=False,
            )
            return self._state
        except Exception:
            self._state = WidgetRenderState(
                status=WidgetStatus.ERROR,
                message="The storefront assistant is unavailable. Please try again.",
                retryable=True,
            )
            return self._state

        view = build_storefront_turn_view(envelope)
        self._state = widget_state_from_turn_view(view)
        return self._state

    def retry(self) -> WidgetRenderState:
        if self._last_user_text is None or not self._state.retryable:
            raise ValueError("retry requires a retryable widget state")
        return self.submit(self._last_user_text)

    def _turn_request(self, user_text: str) -> TurnRequest:
        self._sequence += 1
        return TurnRequest(
            schema_version=SCHEMA_VERSION,
            store_id=self._config.store_id,
            conversation=ConversationRef(
                conversation_id=self._conversation_id,
                message_id=self._message_id_factory(self._sequence),
            ),
            user_text=user_text,
            locale=self._config.locale,
            page_context=self._config.page_context,
        )


def widget_state_from_turn_view(view: StorefrontTurnView) -> WidgetRenderState:
    if view.answer is not None:
        return WidgetRenderState(
            status=WidgetStatus.ANSWER,
            target=view.target,
            constraint_state=view.constraint_state,
            message=view.answer.text,
            evidence=tuple(_evidence_display(item) for item in view.answer.evidence),
            freshness=view.answer.freshness,
            retryable=False,
        )
    if view.fallback is None:
        raise ValueError("turn view must contain answer or fallback")
    return WidgetRenderState(
        status=WidgetStatus.FALLBACK,
        target=view.target,
        constraint_state=view.constraint_state,
        message=view.fallback.message,
        fallback=view.fallback,
        retryable=view.fallback.retryable,
    )


def _evidence_display(evidence: Evidence) -> WidgetEvidenceDisplay:
    return WidgetEvidenceDisplay(
        evidence_id=evidence.evidence_id,
        source=evidence.source,
        field_locator=evidence.field_locator,
        scope=ObjectScope(
            store_id=evidence.store_id,
            product_id=evidence.product_id,
            variant_id=evidence.variant_id,
        ),
        observed_at=evidence.observed_at.isoformat()
        if evidence.observed_at is not None
        else None,
    )


def _validate_exact_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("widget origins must be absolute http(s) origins")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("widget origins must not include paths or query strings")
    normalized = f"{parsed.scheme}://{parsed.netloc}"
    if "*" in normalized:
        raise ValueError("wildcard widget origins are forbidden")
    return normalized


def _scope_title(scope: ObjectScope) -> str:
    if scope.variant_id is None:
        return scope.product_id
    return f"{scope.product_id} / {scope.variant_id}"
