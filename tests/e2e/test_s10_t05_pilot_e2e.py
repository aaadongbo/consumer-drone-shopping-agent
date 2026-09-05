"""Slice 10 local pilot E2E matrix with synthetic read-only dependencies."""

from collections.abc import Iterable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.api import MinimalConversationClient
from backend.application import (
    PilotCompositionConfig,
    PilotMode,
    build_pilot_composition,
)
from backend.catalog import (
    PilotDataReadinessReport,
    PilotLaneReport,
    PilotLaneStatus,
    PilotProductIdentity,
    PilotReadinessStopReason,
    PilotVariantIdentity,
)
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    PageContext,
    TraceOperation,
    TurnRequest,
)
from backend.rag import (
    DocumentChunk,
    DocumentSourceType,
    InMemoryProductRetriever,
    SourceLocator,
)
from backend.shopify import (
    RealShopifyReadAdapter,
    ShopifyTransportFailure,
    ShopifyTransportResult,
)

pytestmark = pytest.mark.e2e

NOW = datetime(2026, 9, 5, 8, 0, tzinfo=UTC)
STORE = "bys-user-store-578412"
STATIC_VERSION = "docs-2026-09-01"
PRODUCTS = (
    ("DJI Air 3", "9278460821642", "50107426603146", 3299),
    ("DJI Mavic 3", "9278439719050", "50107364901002", 7999),
    ("DJI Mini 3", "9278439686282", "50107364802698", 3999),
)
APPROVED_VARIANTS = {
    product_id: variant_id for _, product_id, variant_id, _ in PRODUCTS
}


class SyntheticPilotTransport:
    """Deterministic transport that exposes only the read calls under test."""

    def __init__(
        self,
        *,
        product_id: str,
        variant_id: str,
        price: int = 3299,
        response_variant_id: str | None = None,
        failure: ShopifyTransportFailure | None = None,
    ) -> None:
        self.product_id = product_id
        self.variant_id = variant_id
        self.price = price
        self.response_variant_id = response_variant_id or variant_id
        self.failure = failure
        self.calls: list[str] = []

    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        raise AssertionError("pilot E2E must not read Product for a dynamic question")

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        raise AssertionError("pilot E2E must not read Variants for a dynamic question")

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        self.calls.append("commerce")
        if self.failure is not None:
            return ShopifyTransportResult(failure=self.failure)
        return ShopifyTransportResult(
            payload={
                "variant": {
                    "id": self.response_variant_id,
                    "product_id": self.product_id,
                    "price": f"{self.price}.00",
                    "inventory_quantity": 32,
                    "available_for_sale": True,
                }
            }
        )


class CountingRetriever:
    """Expose the bounded retrieval count without adding a runtime dependency."""

    def __init__(self, chunks: Iterable[DocumentChunk]) -> None:
        self._delegate = InMemoryProductRetriever(
            tuple(chunks), index_version=STATIC_VERSION
        )
        self.calls = 0

    def retrieve(self, request):
        self.calls += 1
        return self._delegate.retrieve(request)


@pytest.mark.parametrize("_product_name,product_id,variant_id,price", PRODUCTS)
def test_all_three_products_have_identity_bound_current_dynamic_journeys(
    _product_name: str, product_id: str, variant_id: str, price: int
) -> None:
    transport = SyntheticPilotTransport(
        product_id=product_id,
        variant_id=variant_id,
        price=price,
    )
    composition, adapter = _composition(
        transport=transport,
        static_chunks=(_static_chunk(product_id),),
    )
    payload = _ask(composition, _turn(product_id, variant_id, "这款现在多少钱？"))

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope.product_id == product_id
    assert payload.resolved_scope.variant_id == variant_id
    assert payload.claims[0].fact.value == price
    assert payload.evidence[0].source == (
        f"shopify://{STORE}/products/{product_id}/variants/{variant_id}/commerce"
    )
    assert payload.freshness is not None
    assert payload.freshness.observed_at == NOW
    assert payload.freshness.source == payload.evidence[0].source
    assert transport.calls == ["commerce"]
    assert len(adapter.call_ledger) == 1
    assert adapter.call_ledger[0].operation is TraceOperation.REFRESH_COMMERCE_STATE
    assert adapter.write_call_count == 0
    _assert_trace(payload, composition)


@pytest.mark.parametrize("_product_name,product_id,variant_id,_price", PRODUCTS)
def test_all_three_products_have_same_product_static_evidence_journeys(
    _product_name: str, product_id: str, variant_id: str, _price: int
) -> None:
    transport = SyntheticPilotTransport(product_id=product_id, variant_id=variant_id)
    composition, adapter = _composition(
        transport=transport,
        static_chunks=(_static_chunk(product_id),),
    )
    payload = _ask(
        composition,
        _turn(product_id, variant_id, "Does this support beginner flight mode?"),
    )

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope.product_id == product_id
    assert payload.resolved_scope.variant_id == variant_id
    assert payload.claims[0].field == "faq"
    assert payload.evidence[0].field_locator == (
        f"rag://drone-travel-faq@{STATIC_VERSION}/chunk/000"
    )
    assert payload.freshness is None
    assert transport.calls == []
    assert adapter.call_ledger == ()
    assert adapter.write_call_count == 0
    _assert_trace(payload, composition)


def test_cross_product_static_injection_is_rejected_before_answer() -> None:
    _, air_product, air_variant, _ = PRODUCTS[0]
    _, mavic_product, _, _ = PRODUCTS[1]
    transport = SyntheticPilotTransport(
        product_id=air_product,
        variant_id=air_variant,
    )
    retriever = CountingRetriever((_static_chunk(mavic_product),))
    composition, adapter = _composition(
        transport=transport,
        static_chunks=(),
        retriever=retriever,
    )

    payload = _ask(
        composition,
        _turn(air_product, air_variant, "Does this support beginner flight mode?"),
    )

    _assert_safe_fallback(payload, FallbackReasonCode.FACT_UNKNOWN_OR_MISSING)
    assert payload.resolved_scope.product_id == air_product
    assert retriever.calls == 2
    assert transport.calls == []
    assert adapter.call_ledger == ()
    assert adapter.write_call_count == 0
    _assert_trace(payload, composition)


def test_variant_identity_mismatch_stops_dynamic_fact_composition() -> None:
    _, product_id, variant_id, _ = PRODUCTS[0]
    transport = SyntheticPilotTransport(
        product_id=product_id,
        variant_id=variant_id,
        response_variant_id="50107364901002",
    )
    composition, adapter = _composition(
        transport=transport,
        static_chunks=(_static_chunk(product_id),),
    )

    payload = _ask(composition, _turn(product_id, variant_id, "这款现在多少钱？"))

    _assert_safe_fallback(payload, FallbackReasonCode.VARIANT_NOT_FOUND)
    assert transport.calls == ["commerce"]
    assert len(adapter.call_ledger) == 1
    assert adapter.write_call_count == 0
    _assert_trace(payload, composition)


def test_shopify_source_failure_is_bounded_and_contains_no_stale_fact() -> None:
    _, product_id, variant_id, _ = PRODUCTS[0]
    transport = SyntheticPilotTransport(
        product_id=product_id,
        variant_id=variant_id,
        failure=ShopifyTransportFailure.TIMEOUT,
    )
    composition, adapter = _composition(
        transport=transport,
        static_chunks=(_static_chunk(product_id),),
    )

    payload = _ask(composition, _turn(product_id, variant_id, "这款现在多少钱？"))

    _assert_safe_fallback(payload, FallbackReasonCode.TOOL_TIMEOUT)
    assert payload.fallback.retryable is True
    assert transport.calls == ["commerce"]
    assert len(adapter.call_ledger) == 1
    assert adapter.last_stop_reason.value == "TIMEOUT"
    assert adapter.write_call_count == 0
    _assert_trace(payload, composition)


def _composition(
    *,
    transport: SyntheticPilotTransport,
    static_chunks: tuple[DocumentChunk, ...],
    retriever: CountingRetriever | None = None,
):
    adapter = RealShopifyReadAdapter(
        transport=transport,
        clock=lambda: NOW,
        approved_store_id=STORE,
        approved_variant_ids=APPROVED_VARIANTS,
        max_read_calls=2,
        max_attempts=1,
    )
    composition = build_pilot_composition(
        PilotCompositionConfig(
            mode=PilotMode.PILOT,
            store_id=STORE,
            shopify=adapter,
            readiness=_ready_report(),
            static_retriever=retriever
            or InMemoryProductRetriever(static_chunks, index_version=STATIC_VERSION),
            clock=lambda: NOW,
            correlation_id_factory=lambda: "correlation-s10-t05",
        )
    )
    return composition, adapter


def _ask(composition, request: TurnRequest):
    client = MinimalConversationClient(TestClient(composition.api))
    return client.ask(request).root


def _turn(product_id: str, variant_id: str, question: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=STORE,
        conversation=ConversationRef(
            conversation_id="conversation-s10-t05",
            message_id=f"message-{product_id}-{len(question)}",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(product_id=product_id, variant_id=variant_id),
    )


def _ready_report() -> PilotDataReadinessReport:
    products = tuple(
        PilotProductIdentity(
            product_name=product_name,
            store_id=STORE,
            product_id=product_id,
            variants=(
                PilotVariantIdentity(
                    store_id=STORE,
                    product_id=product_id,
                    variant_id=variant_id,
                ),
            ),
        )
        for product_name, product_id, variant_id, _price in PRODUCTS
    )
    lane = PilotLaneReport(
        status=PilotLaneStatus.GO,
        stop_reason=PilotReadinessStopReason.READY,
        accepted_product_count=3,
        accepted_variant_count=3,
    )
    return PilotDataReadinessReport(
        store_id=STORE,
        approved_product_names=tuple(item.product_name for item in products),
        shopify_lane=lane,
        corpus_lane=lane,
        accepted_products=products,
        accepted_variant_ids=tuple(item.variants[0].variant_id for item in products),
    )


def _static_chunk(product_id: str) -> DocumentChunk:
    locator = f"rag://drone-travel-faq@{STATIC_VERSION}/chunk/000"
    return DocumentChunk(
        store_id=STORE,
        product_id=product_id,
        source_id="drone-travel-faq",
        source_type=DocumentSourceType.FAQ,
        version=STATIC_VERSION,
        chunk_id=f"faq-{product_id}",
        order=0,
        locator=SourceLocator(
            source_id="drone-travel-faq",
            version=STATIC_VERSION,
            locator=locator,
        ),
        heading_path=("FAQ",),
        text="The aircraft supports beginner flight modes and travel use.",
    )


def _assert_safe_fallback(payload, reason: FallbackReasonCode) -> None:
    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is reason
    assert payload.claims == payload.evidence == payload.bindings == []
    wire = payload.to_wire_json().casefold()
    assert "authorization" not in wire
    assert "bearer" not in wire
    assert "secret" not in wire
    assert "token" not in wire


def _assert_trace(payload, composition) -> None:
    assert payload.trace_correlation_id == "correlation-s10-t05"
    assert {event.correlation_id for event in composition.trace_sink.events} == {
        "correlation-s10-t05"
    }
    assert all(
        "authorization" not in event.model_dump_json().casefold()
        for event in composition.trace_sink.events
    )
    assert all(
        event.summary.operation in {None, TraceOperation.REFRESH_COMMERCE_STATE}
        for event in composition.trace_sink.events
    )
