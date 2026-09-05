"""Integration coverage for the explicit pilot composition and API path."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

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
from backend.common import SCHEMA_VERSION
from backend.rag import (
    DocumentChunk,
    DocumentSourceType,
    InMemoryProductRetriever,
    SourceLocator,
)
from backend.shopify import RealShopifyReadAdapter, ShopifyTransportResult

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 7, 30, tzinfo=UTC)
STORE = "store-dji-cn"
PRODUCT = "9278460821642"
VARIANT = "50107426603146"


class PilotTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        self.calls.append("product")
        return ShopifyTransportResult(
            payload={
                "product": {
                    "id": product_id,
                    "title": "DJI Air 3",
                    "variants": [
                        {
                            "id": VARIANT,
                            "product_id": product_id,
                            "title": "Default Title",
                        }
                    ],
                }
            }
        )

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        self.calls.append("variants")
        return ShopifyTransportResult(payload={"variants": []})

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        self.calls.append("commerce")
        return ShopifyTransportResult(
            payload={
                "variant": {
                    "id": variant_id,
                    "product_id": product_id,
                    "price": "3299.00",
                    "inventory_quantity": 32,
                    "available_for_sale": True,
                }
            }
        )


def test_pilot_api_routes_dynamic_to_shopify_and_static_to_controlled_rag() -> None:
    transport = PilotTransport()
    adapter = RealShopifyReadAdapter(
        transport=transport,
        clock=lambda: NOW,
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
    )
    composition = build_pilot_composition(
        PilotCompositionConfig(
            mode=PilotMode.PILOT,
            store_id=STORE,
            shopify=adapter,
            readiness=_ready_report(),
            static_retriever=InMemoryProductRetriever(
                (_static_chunk(),), index_version="docs-2026-09-01"
            ),
            clock=lambda: NOW,
            correlation_id_factory=lambda: "correlation-s10-t04",
        )
    )
    client = TestClient(composition.api)

    dynamic = client.post(
        "/v1/conversation/turn", json=_turn_payload("这款现在多少钱？")
    )
    static = client.post(
        "/v1/conversation/turn",
        json=_turn_payload("Does this support beginner flight mode?"),
    )

    assert dynamic.status_code == 200
    assert dynamic.json()["outcome"] == "ANSWER"
    assert dynamic.json()["claims"][0]["fact"]["value"] == 3299
    assert dynamic.json()["freshness"]["source"].startswith("shopify://")
    assert static.status_code == 200
    assert static.json()["outcome"] == "ANSWER"
    assert static.json()["evidence"][0]["field_locator"].startswith("rag://")
    assert transport.calls == ["commerce"]
    assert adapter.write_call_count == 0
    assert all(item.classification.value == "read" for item in adapter.call_ledger)
    assert {event.correlation_id for event in composition.trace_sink.events} == {
        "correlation-s10-t04"
    }


def _turn_payload(user_text: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "store_id": STORE,
        "conversation": {
            "conversation_id": "conversation-s10-t04",
            "message_id": f"message-{len(user_text)}",
        },
        "user_text": user_text,
        "locale": "zh-CN",
        "page_context": {"product_id": PRODUCT, "variant_id": VARIANT},
    }


def _ready_report() -> PilotDataReadinessReport:
    products = tuple(
        PilotProductIdentity(
            product_name=name,
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
        for name, product_id, variant_id in (
            ("DJI Air 3", PRODUCT, VARIANT),
            ("DJI Mavic 3", "9278439719050", "50107364901002"),
            ("DJI Mini 3", "9278439686282", "50107364802698"),
        )
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


def _static_chunk() -> DocumentChunk:
    return DocumentChunk(
        store_id=STORE,
        product_id=PRODUCT,
        source_id="drone-travel-faq",
        source_type=DocumentSourceType.FAQ,
        version="docs-2026-09-01",
        chunk_id="air-faq-000",
        order=0,
        locator=SourceLocator(
            source_id="drone-travel-faq",
            version="docs-2026-09-01",
            locator="rag://drone-travel-faq@docs-2026-09-01/chunk/000",
        ),
        heading_path=("FAQ",),
        text="The aircraft supports beginner flight modes and travel use.",
    )
