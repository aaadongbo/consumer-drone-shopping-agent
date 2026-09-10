"""Explicit fixture/pilot composition for the Slice 10 local pilot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from fastapi import FastAPI

from backend.agent import (
    BoundedProductRagLoop,
    IntentAdapterBudget,
    IntentRoute,
    ProductRagBudget,
    ProductRagRetriever,
    RestrictedIntentAdapter,
    RestrictedIntentRouter,
)
from backend.application.product_rag import (
    ProductRagApplicationService,
    ProductRagQuestionInterpreter,
)
from backend.application.slice_1 import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
    is_out_of_scope_question,
)
from backend.catalog import PILOT_PRODUCT_COUNT, PilotDataReadinessReport
from backend.common import AnswerEnvelope, ObjectScope, TurnRequest
from backend.conversation import (
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)
from backend.shopify import (
    DeterministicShopifyFixture,
    RealShopifyReadAdapter,
    ShopifyReadPort,
)


class PilotMode(StrEnum):
    """The only two supported local runtime selections."""

    FIXTURE = "fixture"
    PILOT = "pilot"


class PilotCompositionError(ValueError):
    """Safe configuration error that carries no credential or source details."""


@dataclass(frozen=True, slots=True)
class PilotCompositionConfig:
    """All dependencies required to construct one explicit local composition."""

    mode: PilotMode
    store_id: str
    shopify: ShopifyReadPort
    static_retriever: ProductRagRetriever
    readiness: PilotDataReadinessReport | None = None
    rag_budget: ProductRagBudget | None = None
    intent_adapter: RestrictedIntentAdapter | None = None
    intent_budget: IntentAdapterBudget | None = None
    clock: Callable[[], datetime] | None = None
    correlation_id_factory: Callable[[], str] | None = None


@dataclass(frozen=True, slots=True)
class PilotComposition:
    """Constructed application/API pair and its observable local boundaries."""

    mode: PilotMode
    store_id: str
    shopify: ShopifyReadPort
    application: PilotConversationApplication
    api: FastAPI
    trace_sink: InMemoryTraceSink


class PilotConversationApplication:
    """Route static and dynamic questions without switching runtime modes."""

    def __init__(
        self,
        *,
        store_id: str,
        commerce: Slice1ApplicationService,
        static: ProductRagApplicationService,
        intent_router: RestrictedIntentRouter,
    ) -> None:
        self._store_id = store_id
        self._commerce = commerce
        self._static = static
        self._intent_router = intent_router

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        if request.store_id != self._store_id:
            raise PilotCompositionError("request store is outside the pilot scope")
        # Keep the live pilot on the typed commerce handoff path for orders,
        # refunds, shipping, and account questions.  The restricted intent
        # adapter is deliberately only a pre-sales router and must not turn an
        # out-of-scope request into a static Product RAG answer.
        if is_out_of_scope_question(request.user_text):
            return self._commerce.answer(request)
        decision = self._intent_router.decide(request)
        if decision.route is IntentRoute.COMMERCE_FACT:
            try:
                return self._commerce.answer(request)
            except Exception:
                # A bounded route suggestion cannot let an unsupported exact
                # interpreter path escape the public answer boundary.
                return self._static.fallback_resolved(
                    request,
                    _page_context_resolution(request),
                )
        if decision.route is IntentRoute.SAFE_FALLBACK:
            return self._static.fallback_resolved(
                request,
                _page_context_resolution(request),
            )
        return self._static.answer_resolved(
            request,
            _page_context_resolution(request),
        )


def build_pilot_composition(config: PilotCompositionConfig) -> PilotComposition:
    """Build the explicitly requested mode, refusing implicit adapter fallback."""
    # Import after this module is initialized so API guardrails cannot form a
    # package-initialization cycle through the runtime composition boundary.
    from backend.api import create_conversation_api

    mode = _coerce_mode(config.mode)
    _validate_config(config, mode)
    clock = config.clock or (lambda: datetime.now(UTC))
    correlation_id_factory = config.correlation_id_factory or (
        lambda: f"pilot-{uuid4().hex}"
    )
    trace_sink = InMemoryTraceSink()
    commerce = Slice1ApplicationService(
        shopify=config.shopify,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=trace_sink,
        correlation_id_factory=correlation_id_factory,
        clock=clock,
    )
    static = ProductRagApplicationService(
        loop=BoundedProductRagLoop(
            retriever=config.static_retriever,
            budget=config.rag_budget,
        ),
        interpreter=ProductRagQuestionInterpreter(),
        trace_sink=trace_sink,
        correlation_id_factory=correlation_id_factory,
        clock=clock,
        retriever=config.static_retriever,
    )
    intent_router = RestrictedIntentRouter(
        adapter=config.intent_adapter,
        budget=config.intent_budget
        or IntentAdapterBudget(
            timeout_ms=8_000,
            max_model_tokens=1_200,
        ),
    )
    application = PilotConversationApplication(
        store_id=config.store_id,
        commerce=commerce,
        static=static,
        intent_router=intent_router,
    )
    return PilotComposition(
        mode=mode,
        store_id=config.store_id,
        shopify=config.shopify,
        application=application,
        api=create_conversation_api(application),
        trace_sink=trace_sink,
    )


def _coerce_mode(mode: PilotMode | str) -> PilotMode:
    try:
        return PilotMode(mode)
    except ValueError as error:
        raise PilotCompositionError("runtime mode must be fixture or pilot") from error


def _validate_config(config: PilotCompositionConfig, mode: PilotMode) -> None:
    if not isinstance(config.store_id, str) or not config.store_id.strip():
        raise PilotCompositionError("pilot store scope is required")
    if config.shopify is None or config.static_retriever is None:
        raise PilotCompositionError("shopify and static retriever are required")
    if mode is PilotMode.FIXTURE:
        if not isinstance(config.shopify, DeterministicShopifyFixture):
            raise PilotCompositionError(
                "fixture mode requires the configured fixture adapter"
            )
        return
    if not isinstance(config.shopify, RealShopifyReadAdapter):
        raise PilotCompositionError("pilot mode requires the live read adapter")
    readiness = config.readiness
    if readiness is None or not readiness.ready:
        raise PilotCompositionError("pilot readiness is not accepted")
    if readiness.store_id != config.store_id:
        raise PilotCompositionError("pilot readiness store does not match config")
    if len(readiness.accepted_products) != PILOT_PRODUCT_COUNT:
        raise PilotCompositionError("pilot readiness product scope is incomplete")


def _page_context_resolution(request: TurnRequest) -> TargetResolution:
    scope = ObjectScope(
        store_id=request.store_id,
        product_id=request.page_context.product_id,
        variant_id=request.page_context.variant_id,
    )
    return TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.SINGLE_OBJECT,
            object_scope=scope,
        ),
        resolution_source=ResolutionSource.PAGE_CONTEXT,
        context_action=ContextAction.KEEP,
    )


__all__ = [
    "PilotComposition",
    "PilotCompositionConfig",
    "PilotCompositionError",
    "PilotConversationApplication",
    "PilotMode",
    "build_pilot_composition",
]
