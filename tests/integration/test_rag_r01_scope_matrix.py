"""RAG-R01 Product-shared and exact-Variant retrieval matrix."""

import pytest

from backend.rag import (
    ChunkBaselineManifest,
    ChunkBaselineRecord,
    ChunkBaselineStopReason,
    ControlledRetrievalRequest,
    retrieve_controlled_chunk_metadata,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("retrieval_request", "expected_chunk_ids"),
    [
        (
            ControlledRetrievalRequest(
                store_id="store-a",
                product_id="product-a",
                query="battery",
            ),
            ("shared-a",),
        ),
        (
            ControlledRetrievalRequest(
                store_id="store-a",
                product_id="product-a",
                variant_id="variant-a",
                query="battery",
            ),
            ("shared-a", "variant-a"),
        ),
        (
            ControlledRetrievalRequest(
                store_id="store-a",
                product_id="product-a",
                variant_id="variant-b",
                query="battery",
            ),
            ("shared-a", "variant-b"),
        ),
    ],
)
def test_scope_matrix_keeps_product_shared_and_exact_variant_records(
    retrieval_request: ControlledRetrievalRequest,
    expected_chunk_ids: tuple[str, ...],
) -> None:
    result = retrieve_controlled_chunk_metadata(_manifest(), retrieval_request)

    assert result.stop_reason is None
    assert tuple(candidate.chunk_id for candidate in result.candidates) == (
        *expected_chunk_ids,
    )


@pytest.mark.parametrize(
    "retrieval_request",
    [
        ControlledRetrievalRequest(
            store_id="store-b",
            product_id="product-a",
            variant_id="variant-a",
            query="battery",
        ),
        ControlledRetrievalRequest(
            store_id="store-a",
            product_id="product-b",
            variant_id="variant-a",
            query="battery",
        ),
        ControlledRetrievalRequest(
            store_id="store-a",
            product_id="product-a",
            variant_id="variant-a",
            query="bundleb",
        ),
        ControlledRetrievalRequest(
            store_id="store-a",
            product_id="product-a",
            query="variant-only",
        ),
    ],
)
def test_cross_store_product_variant_and_product_only_scope_fail_closed(
    retrieval_request: ControlledRetrievalRequest,
) -> None:
    result = retrieve_controlled_chunk_metadata(_manifest(), retrieval_request)

    assert result.candidates == ()
    assert result.stop_reason is ChunkBaselineStopReason.NO_SCOPED_MATCH


def _manifest() -> ChunkBaselineManifest:
    return ChunkBaselineManifest(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        status="APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT",
        corpus_version="v0.1",
        append_only=True,
        corpus_manifest_sha256="1" * 64,
        source_inventory_sha256="2" * 64,
        records=(
            _record("shared-a", "store-a", "product-a", None, ("battery",)),
            _record("variant-a", "store-a", "product-a", "variant-a", ("battery",)),
            _record(
                "variant-b",
                "store-a",
                "product-a",
                "variant-b",
                ("battery", "bundleb"),
            ),
            _record(
                "variant-only",
                "store-a",
                "product-a",
                "variant-a",
                ("variant-only",),
            ),
        ),
    )


def _record(
    chunk_id: str,
    store_id: str,
    product_id: str,
    variant_id: str | None,
    keywords: tuple[str, ...],
) -> ChunkBaselineRecord:
    source_id = f"source-{chunk_id}"
    return ChunkBaselineRecord(
        chunk_id=chunk_id,
        source_id=source_id,
        source_ref=f"ref-{source_id}",
        source_version="v1",
        corpus_version="v0.1",
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        language="zh-CN",
        region="China mainland",
        page_number=1,
        ordinal_start=0,
        ordinal_end=1,
        extraction_method="metadata-only fixture",
        text_sha256="c" * 64,
        locator=f"rag://{source_id}@v1/page/1#ord=0-1",
        token_estimate=1,
        keywords=keywords,
    )
