"""RAG-R04 coverage for injecting the external adapter into the pilot."""

import hashlib
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
    ChunkBaselineManifest,
    ChunkBaselineRecord,
    ControlledRetrievalCandidate,
    ControlledRetrievalRequest,
    ControlledRetrievalResult,
    CorpusReadinessReport,
    CorpusReadinessStopReason,
    CorpusScopeBinding,
    CorpusScopeBindingRegistry,
    DocumentChunk,
    DocumentSourceType,
    ExternalCorpusProductRetriever,
    ExternalCorpusReadResult,
    ExternalCorpusStopReason,
    SourceLocator,
)
from backend.shopify import RealShopifyReadAdapter, ShopifyTransportResult

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 8, 0, tzinfo=UTC)
STORE = "store-dji-cn"
PRODUCT = "9278460821642"
VARIANT = "50107426603146"
MANIFEST_SHA256 = "1" * 64
SOURCE_VERSION = "docs-2026-09-01"
SOURCE_ID = "drone-travel-package-list"
LOCATOR = f"rag://{SOURCE_ID}@{SOURCE_VERSION}/chunk/000"
TEXT = "Travel Pack includes three batteries."
TEXT_SHA256 = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


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
                    "variants": [{"id": VARIANT, "product_id": product_id}],
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


class AcceptedExternalReader:
    def __init__(self) -> None:
        self.calls: list[ControlledRetrievalRequest] = []

    def retrieve(
        self, *, chunk_manifest_path: str, request: ControlledRetrievalRequest
    ) -> ExternalCorpusReadResult:
        self.calls.append(request)
        record = _record(request)
        candidate = ControlledRetrievalCandidate(
            chunk_id=record.chunk_id,
            source_id=record.source_id,
            source_ref=record.source_ref,
            locator=record.locator,
            product_id=record.product_id,
            variant_id=record.variant_id,
            page_number=record.page_number,
            ordinal_start=record.ordinal_start,
            ordinal_end=record.ordinal_end,
            score=1,
            text_sha256=record.text_sha256,
            token_estimate=record.token_estimate,
        )
        return ExternalCorpusReadResult(
            request=request,
            chunks=(_chunk(record),),
            metadata_result=ControlledRetrievalResult(
                request=request,
                candidates=(candidate,),
                action_rounds_used=1,
                retrieval_tokens_used=record.token_estimate,
                metadata_digest="d" * 64,
            ),
            corpus_report=CorpusReadinessReport(
                manifest_path="/external/manifest.json",
                manifest_sha256=MANIFEST_SHA256,
                source_count=1,
                page_locator_count=1,
                stop_reason=CorpusReadinessStopReason.CORPUS_NOT_INDEXED,
            ),
            manifest=_manifest(record),
            stop_reason=ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED,
        )


def test_pilot_accepts_external_static_adapter_and_preserves_source_scope() -> None:
    transport = PilotTransport()
    reader = AcceptedExternalReader()
    composition = build_pilot_composition(
        PilotCompositionConfig(
            mode=PilotMode.PILOT,
            store_id=STORE,
            shopify=RealShopifyReadAdapter(
                transport=transport,
                clock=lambda: NOW,
                approved_store_id=STORE,
                approved_variant_ids={PRODUCT: VARIANT},
            ),
            readiness=_ready_report(),
            static_retriever=ExternalCorpusProductRetriever(
                reader=reader,  # type: ignore[arg-type]
                chunk_manifest_path="/external/corrected-chunks.manifest.json",
                binding_registry=CorpusScopeBindingRegistry(
                    bindings=(
                        CorpusScopeBinding(
                            corpus_store_id="corpus-store-dji-cn",
                            corpus_product_key="corpus-air-3",
                            corpus_variant_key="corpus-air-3-default",
                            manifest_sha256=MANIFEST_SHA256,
                            canonical_scope={
                                "store_id": STORE,
                                "product_id": PRODUCT,
                                "variant_id": VARIANT,
                            },
                        ),
                    )
                ),
                manifest_sha256=MANIFEST_SHA256,
            ),
            clock=lambda: NOW,
            correlation_id_factory=lambda: "correlation-rag-r04",
        )
    )
    client = TestClient(composition.api)

    static = client.post(
        "/v1/conversation/turn", json=_turn_payload("How many batteries are included?")
    )
    dynamic = client.post(
        "/v1/conversation/turn", json=_turn_payload("这款现在多少钱？")
    )

    assert static.status_code == 200
    assert static.json()["outcome"] == "ANSWER"
    assert static.json()["evidence"][0]["field_locator"] == LOCATOR
    assert static.json()["evidence"][0].get("variant_id") is None
    assert dynamic.status_code == 200
    assert dynamic.json()["outcome"] == "ANSWER"
    assert dynamic.json()["claims"][0]["fact"]["value"] == 3299
    assert reader.calls and len(reader.calls) == 1
    assert reader.calls[0].variant_id == VARIANT
    assert transport.calls == ["commerce"]


def _turn_payload(user_text: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "store_id": STORE,
        "conversation": {
            "conversation_id": "conversation-rag-r04",
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


def _record(request: ControlledRetrievalRequest) -> ChunkBaselineRecord:
    return ChunkBaselineRecord(
        chunk_id="air-package-000",
        source_id=SOURCE_ID,
        source_ref="air-3-package",
        source_version=SOURCE_VERSION,
        corpus_version="v0.1",
        store_id=request.store_id,
        product_id=request.product_id,
        variant_id=None,
        language="zh-CN",
        region="China mainland",
        page_number=1,
        ordinal_start=0,
        ordinal_end=2,
        extraction_method="injected external reader",
        text_sha256=TEXT_SHA256,
        locator=LOCATOR,
        token_estimate=6,
        keywords=("battery", "package"),
    )


def _manifest(record: ChunkBaselineRecord) -> ChunkBaselineManifest:
    return ChunkBaselineManifest(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        status="APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT",
        corpus_version="v0.1",
        append_only=True,
        corpus_manifest_sha256=MANIFEST_SHA256,
        source_inventory_sha256="2" * 64,
        records=(record,),
    )


def _chunk(record: ChunkBaselineRecord) -> DocumentChunk:
    identity = "rag-corrected-chunk-baseline-v0.1:v0.1:" + MANIFEST_SHA256
    return DocumentChunk(
        store_id=record.store_id,
        product_id=record.product_id,
        variant_id=record.variant_id,
        source_id=record.source_id,
        source_type=DocumentSourceType.MANUAL,
        version=record.source_version,
        chunk_id=record.chunk_id,
        order=0,
        locator=SourceLocator(
            source_id=record.source_id,
            version=record.source_version,
            locator=record.locator,
        ),
        heading_path=(record.source_ref, "battery"),
        text=TEXT,
        metadata={
            "corpus_version": record.corpus_version,
            "source_ref": record.source_ref,
            "page_number": str(record.page_number),
            "ordinal_start": str(record.ordinal_start),
            "ordinal_end": str(record.ordinal_end),
            "extraction_method": record.extraction_method,
            "text_sha256": record.text_sha256,
            "locator": record.locator,
            "language": record.language,
            "region": record.region,
            "manifest_identity": identity,
        },
    )
