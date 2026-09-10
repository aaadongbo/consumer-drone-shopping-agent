"""T09 actual application-path English acceptance fixtures."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.agent import (
    BoundedProductRagLoop,
    IntentAdapterBudget,
    RestrictedIntentRouter,
)
from backend.application.pilot_composition import PilotConversationApplication
from backend.application.product_rag import (
    ProductRagApplicationService,
    ProductRagQuestionInterpreter,
)
from backend.application.slice_1 import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    EnvelopeOutcome,
    ObjectScope,
    PageContext,
    TurnRequest,
)
from backend.rag import DocumentManifest, InMemoryProductRetriever, chunk_manifest
from backend.shopify import (
    RealShopifyReadAdapter,
    ShopifyTransportResult,
)

pytestmark = pytest.mark.integration

STORE = "shopify-store:bys-user-store-578412-7a11gk0u"
PRODUCT = "9278439686282"
VARIANT = "50107364802698"
_RAG_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def _request(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=STORE,
        conversation=ConversationRef(conversation_id="t09-flow", message_id=text),
        user_text=text,
        locale="en-US",
        page_context=PageContext(product_id=PRODUCT, variant_id=VARIANT),
    )


class _UsCommerceTransport:
    def read_product(self, *, store_id: str, product_id: str):
        return ShopifyTransportResult(
            payload={
                "product": {
                    "id": product_id,
                    "title": "DJI Mini 3",
                    "variants": [
                        {
                            "id": VARIANT,
                            "product_id": product_id,
                            "title": "Default Title",
                        }
                    ],
                }
            },
            http_status=200,
        )

    def read_variants(self, *, store_id: str, product_id: str):
        return ShopifyTransportResult(
            payload={
                "variants": [
                    {
                        "id": VARIANT,
                        "product_id": product_id,
                        "title": "Default Title",
                    }
                ]
            },
            http_status=200,
        )

    def read_commerce_state(self, *, store_id: str, product_id: str, variant_id: str):
        return ShopifyTransportResult(
            payload={
                "variant": {
                    "id": variant_id,
                    "product_id": product_id,
                    "title": "Default Title",
                    "price": "549.00",
                    "inventory_quantity": 7,
                    "available_for_sale": True,
                }
            },
            http_status=200,
        )


def test_application_path_answers_price_and_handoffs_order_questions() -> None:
    shopify = RealShopifyReadAdapter(
        transport=_UsCommerceTransport(),
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
        commerce_currency="USD",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )
    service = Slice1ApplicationService(
        shopify=shopify,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-flow-correlation",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )
    answer = service.answer(_request("How much does this cost?")).root
    handoff = service.answer(_request("Where is my order?")).root
    assert answer.outcome is EnvelopeOutcome.ANSWER
    assert "current price" in answer.text
    assert answer.evidence[0].fact is not None
    assert answer.evidence[0].fact.unit == "USD"
    assert handoff.outcome is EnvelopeOutcome.FALLBACK
    assert "orders" in handoff.text
    assert shopify.write_call_count == 0


def test_pilot_path_routes_order_questions_to_typed_handoff_before_intent_router() -> (
    None
):
    shopify = RealShopifyReadAdapter(
        transport=_UsCommerceTransport(),
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
        commerce_currency="USD",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )
    commerce = Slice1ApplicationService(
        shopify=shopify,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-handoff-correlation",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )

    class _StaticMustNotRun:
        def answer_resolved(self, *args, **kwargs):
            raise AssertionError("order question reached static RAG")

        def fallback_resolved(self, *args, **kwargs):
            raise AssertionError("order question reached static fallback")

    class _RouterMustNotRun:
        def decide(self, request):
            raise AssertionError("order question reached intent router")

    application = PilotConversationApplication(
        store_id=STORE,
        commerce=commerce,
        static=_StaticMustNotRun(),
        intent_router=_RouterMustNotRun(),
    )
    payload = application.answer(_request("Where is my order?")).root
    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code.value == "OUT_OF_SCOPE"
    assert shopify.write_call_count == 0


def test_live_pilot_does_not_promote_single_chunk_to_multi_product_claim() -> None:
    """A single page-scoped retrieval cannot answer a multi-product task."""

    manifest = DocumentManifest.model_validate_json(
        _RAG_FIXTURE.read_text(encoding="utf-8")
    )
    retriever = InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    )
    static = ProductRagApplicationService(
        loop=BoundedProductRagLoop(retriever=retriever, clock_ms=lambda: 0),
        interpreter=ProductRagQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-compare-correlation",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
        retriever=retriever,
    )
    shopify = RealShopifyReadAdapter(
        transport=_UsCommerceTransport(),
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
        commerce_currency="USD",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )
    commerce = Slice1ApplicationService(
        shopify=shopify,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-compare-commerce",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )
    application = PilotConversationApplication(
        store_id=STORE,
        commerce=commerce,
        static=static,
        intent_router=RestrictedIntentRouter(
            budget=IntentAdapterBudget(timeout_ms=100, max_model_tokens=100)
        ),
    )

    for question in (
        "Compare this with another drone",
        "Which drone do you recommend for travel?",
    ):
        payload = application.answer(_request(question)).root
        assert payload.outcome is EnvelopeOutcome.FALLBACK
        assert payload.claims == payload.evidence == payload.bindings == []
        assert "rag://" not in payload.text


def test_live_pilot_requires_explicit_us_variant_package_evidence() -> None:
    """Legacy fixture metadata cannot prove a US Variant package claim."""

    manifest = DocumentManifest.model_validate_json(
        _RAG_FIXTURE.read_text(encoding="utf-8")
    )
    retriever = InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    )
    service = ProductRagApplicationService(
        loop=BoundedProductRagLoop(retriever=retriever, clock_ms=lambda: 0),
        interpreter=ProductRagQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-package-correlation",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
        retriever=retriever,
    )
    payload = service.answer_resolved(
        _request("How many batteries are in the package?"),
        _page_context_resolution(_request("How many batteries are in the package?")),
    ).root
    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.claims == payload.evidence == payload.bindings == []


def _page_context_resolution(request: TurnRequest):
    from backend.conversation import (
        ContextAction,
        ResolutionSource,
        TargetResolution,
        TurnTarget,
        TurnTargetKind,
    )

    return TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.SINGLE_OBJECT,
            object_scope=ObjectScope(
                store_id=request.store_id,
                product_id=request.page_context.product_id,
                variant_id=request.page_context.variant_id,
            ),
        ),
        resolution_source=ResolutionSource.PAGE_CONTEXT,
        context_action=ContextAction.KEEP,
    )
