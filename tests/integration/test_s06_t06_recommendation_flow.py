"""Integration coverage for the Slice 6 recommendation walking skeleton."""

from datetime import UTC, datetime

import pytest

from backend.application import MultiProductRecommendationService
from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import (
    SCHEMA_VERSION,
    AttributeStatus,
    AttributeValue,
    ConversationRef,
    PageContext,
    ToolResult,
    ToolStatus,
    TurnRequest,
)
from backend.rag import (
    DocumentChunk,
    DocumentSourceType,
    RetrievalResult,
    RetrievalStrategy,
    SourceLocator,
)
from backend.shopify import CommerceState

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 3, tzinfo=UTC)
_STORE_ID = "store-s02-alpha"


class CatalogCommerceReadDouble:
    """Test-only read port backed by the deterministic Slice 2 catalog fixture."""

    def __init__(self) -> None:
        self.snapshot: CatalogFixtureSnapshot = DeterministicCatalogFixture(
            observed_at=_NOW
        ).load_store(store_id=_STORE_ID)
        self.calls: list[tuple[str, str, str]] = []
        self.writes = 0

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult[CommerceState]:
        self.calls.append((store_id, product_id, variant_id))
        for item in self.snapshot.commerce:
            if (item.store_id, item.product_id, item.variant_id) == (
                store_id,
                product_id,
                variant_id,
            ):
                return item.result
        raise AssertionError("refresh crossed the catalog identity boundary")


def _request(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=_STORE_ID,
        conversation=ConversationRef(conversation_id="s06-flow", message_id=text),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )


def _service(port: CatalogCommerceReadDouble) -> MultiProductRecommendationService:
    return MultiProductRecommendationService(
        catalog=DeterministicCatalogFixture(observed_at=_NOW),
        shopify=port,
        correlation_id_factory=lambda: "s06-flow-trace",
        clock=lambda: _NOW,
    )


def test_flow_returns_at_most_three_candidates_with_current_commerce() -> None:
    port = CatalogCommerceReadDouble()
    result = _service(port).recommend(_request("预算 6000 元，适合旅行"))

    assert result.fallback is None
    assert 1 <= len(result.candidates) <= 3
    product_ids = {item.candidate.product_id for item in result.candidates}
    assert len(product_ids) == len(result.candidates)
    assert "drone-travel" in product_ids
    assert len(port.calls) == len(result.candidates)
    assert port.writes == 0
    assert all(event.correlation_id == result.correlation_id for event in result.trace)
    assert result.action_plan is not None
    assert len(result.action_round_traces) <= 2
    assert all(item.budget_tool_calls <= 2 for item in result.action_round_traces)
    for candidate in result.candidates:
        assert candidate.evidence_bundle.candidate == candidate.candidate
        assert candidate.explanation.explanation is not None
        assert candidate.evidence_bundle.derived_evidence


def test_no_match_produces_fallback_without_formal_candidates() -> None:
    port = CatalogCommerceReadDouble()
    result = _service(port).recommend(_request("预算 1 元"))

    assert result.candidates == ()
    assert result.fallback is not None
    assert result.fallback.reason.value == "NO_MATCH"
    assert result.trace[-1].event_type.value == "FALLBACK"
    assert port.writes == 0


def test_critical_price_gap_becomes_global_fallback() -> None:
    class MissingPricePort(CatalogCommerceReadDouble):
        def refresh_commerce_state(self, **kwargs):  # type: ignore[no-untyped-def]
            result = super().refresh_commerce_state(**kwargs)
            assert result.data is not None
            data = {
                field: fact for field, fact in result.data.items() if field != "price"
            }
            return result.model_copy(
                update={
                    "status": ToolStatus.SUCCESS,
                    "data": data,
                    "missing_fields": [],
                }
            )

    result = _service(MissingPricePort()).recommend(_request("适合旅行"))

    assert result.candidates == ()
    assert result.fallback is not None
    assert result.fallback.reason.value == "COVERAGE_BELOW_THRESHOLD"


def test_foreign_rag_result_is_discarded() -> None:
    class ForeignRetriever:
        def retrieve(self, request):  # type: ignore[no-untyped-def]
            chunk = DocumentChunk(
                store_id=_STORE_ID,
                product_id="drone-cinema",
                variant_id="cinema-pro",
                source_id="foreign-source",
                source_type=DocumentSourceType.MANUAL,
                version="v1",
                chunk_id="foreign-1",
                order=0,
                locator=SourceLocator(
                    source_id="foreign-source",
                    version="v1",
                    locator="rag://foreign-source@v1/chunk/0",
                ),
                heading_path=("Manual",),
                text="foreign product evidence",
            )
            return RetrievalResult(
                request=request,
                evidence=(chunk,),
                retrieval_strategy=RetrievalStrategy.KEYWORD_OVERLAP,
                index_version="v1",
                filtered_out_count=0,
            )

    port = CatalogCommerceReadDouble()
    result = MultiProductRecommendationService(
        catalog=DeterministicCatalogFixture(observed_at=_NOW),
        shopify=port,
        retriever=ForeignRetriever(),
        correlation_id_factory=lambda: "s06-foreign-rag",
        clock=lambda: _NOW,
    ).recommend(_request("预算 6000 元"))
    assert result.candidates
    assert all(not item.evidence_bundle.rag_evidence for item in result.candidates)
    assert any(
        item.final_stop_reason == "RAG_SCOPE_MISMATCH"
        for item in result.action_round_traces
    )


def test_catalog_price_cannot_replace_current_commerce_price() -> None:
    base = DeterministicCatalogFixture(observed_at=_NOW).load_store(store_id=_STORE_ID)
    first = base.products[0]
    priced = first.model_copy(
        update={
            "shared_attributes": {
                **first.shared_attributes,
                "price": AttributeValue(
                    status=AttributeStatus.KNOWN,
                    value=1,
                    source_ref="fixture://catalog-price",
                ),
            }
        }
    )

    class CatalogWithStaticPrice:
        def load_store(self, *, store_id: str):  # type: ignore[no-untyped-def]
            return CatalogFixtureSnapshot(
                store_id=base.store_id,
                products=(priced, *base.products[1:]),
                variants=base.variants,
                commerce=base.commerce,
            )

    result = MultiProductRecommendationService(
        catalog=CatalogWithStaticPrice(),
        shopify=CatalogCommerceReadDouble(),
        correlation_id_factory=lambda: "s06-static-price",
        clock=lambda: _NOW,
    ).recommend(_request("适合旅行"))

    assert result.candidates
    for item in result.candidates:
        assert all(
            evidence.field != "price"
            for evidence in item.evidence_bundle.catalog_evidence
        )
        assert any(
            evidence.field == "price"
            for evidence in item.evidence_bundle.commerce_evidence
        )
