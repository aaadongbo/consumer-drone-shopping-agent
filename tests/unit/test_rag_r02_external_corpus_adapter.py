"""RAG-R02 external corpus adapter and version boundary coverage."""

from dataclasses import replace

import pytest

from backend.common import ObjectScope
from backend.rag import (
    ChunkBaselineManifest,
    ChunkBaselineRecord,
    CorpusManifestIdentity,
    CorpusScopeBinding,
    CorpusSourceVersion,
    ExternalCorpusAdapterError,
    ExternalCorpusReadResult,
    ExternalCorpusStopReason,
    RetrievalRequest,
    adapt_external_corpus_result,
    build_controlled_retrieval_request,
    retrieve_external_corpus,
)
from backend.rag.controlled_retrieval import (
    ControlledRetrievalCandidate,
    ControlledRetrievalResult,
)
from backend.rag.corpus_readiness import (
    CorpusReadinessReport,
    CorpusReadinessStopReason,
)
from backend.rag.manifest import DocumentChunk, DocumentSourceType, SourceLocator

pytestmark = pytest.mark.unit

MANIFEST_SHA256 = "1" * 64


def test_request_translation_keeps_scope_and_all_reader_budgets() -> None:
    request = RetrievalRequest(
        turn_target=ObjectScope(
            store_id="store-a",
            product_id="product-a",
            variant_id="variant-a",
        ),
        question="battery",
        k=4,
        field_hint="package",
        max_retrieval_tokens=120,
    )

    controlled = build_controlled_retrieval_request(
        request,
        binding=_binding(variant_id="variant-a"),
        manifest_sha256=MANIFEST_SHA256,
        max_action_rounds=1,
        turn_deadline_ms=500,
    )

    assert controlled.store_id == "store-a"
    assert controlled.product_id == "product-a"
    assert controlled.variant_id == "variant-a"
    assert controlled.query == "battery"
    assert controlled.max_candidates == 4
    assert controlled.field_hint == "package"
    assert controlled.max_retrieval_tokens == 120
    assert controlled.max_action_rounds == 1
    assert controlled.turn_deadline_ms == 500


def test_accepted_read_maps_manifest_identity_separately_from_source_version() -> None:
    adapted = adapt_external_corpus_result(_accepted_read())

    assert adapted.accepted is True
    assert adapted.manifest_identity == CorpusManifestIdentity(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        corpus_version="v0.1",
        manifest_sha256=MANIFEST_SHA256,
    )
    assert adapted.retrieval is not None
    assert adapted.retrieval.index_version == (
        "rag-corrected-chunk-baseline-v0.1:v0.1:" + MANIFEST_SHA256
    )
    assert adapted.retrieval.evidence[0].version == "source-v1"
    assert adapted.source_versions == (
        CorpusSourceVersion(source_id="source-a", version="source-v1"),
    )
    assert adapted.filtered_out_count == 2
    assert adapted.retrieval.filtered_out_count == 2


def test_adapter_does_not_repeat_reader_retrieval() -> None:
    class _CountingReader:
        def __init__(self, result: ExternalCorpusReadResult) -> None:
            self.result = result
            self.calls = 0

        def retrieve(self, **_: object) -> ExternalCorpusReadResult:
            self.calls += 1
            return self.result

    reader = _CountingReader(_accepted_read())
    request = RetrievalRequest(
        turn_target=ObjectScope(store_id="store-a", product_id="product-a"),
        question="battery",
    )

    adapted = retrieve_external_corpus(
        reader,  # type: ignore[arg-type]
        chunk_manifest_path="/tmp/metadata-only-fixture.json",
        request=request,
        binding=_binding(),
        manifest_sha256=MANIFEST_SHA256,
    )

    assert adapted.accepted is True
    assert reader.calls == 1


@pytest.mark.parametrize(
    ("stop_reason", "expected_reason"),
    [
        (
            ExternalCorpusStopReason.SOURCE_REGION_INVALID,
            ExternalCorpusStopReason.SOURCE_REGION_INVALID,
        ),
        (
            ExternalCorpusStopReason.TURN_DEADLINE,
            ExternalCorpusStopReason.TURN_DEADLINE,
        ),
    ],
)
def test_failed_read_stops_before_retrieval_result(
    stop_reason: ExternalCorpusStopReason,
    expected_reason: ExternalCorpusStopReason,
) -> None:
    adapted = adapt_external_corpus_result(
        replace(_accepted_read(), stop_reason=stop_reason, chunks=())
    )

    assert adapted.retrieval is None
    assert adapted.accepted is False
    assert adapted.stop_reason is expected_reason


def test_accepted_empty_read_has_explicit_empty_stop_reason() -> None:
    adapted = adapt_external_corpus_result(
        replace(_accepted_read(), chunks=(), metadata_result=None)
    )

    assert adapted.retrieval is None
    assert adapted.stop_reason is ExternalCorpusStopReason.EMPTY_RESULT


def test_source_version_mismatch_stops_before_evidence() -> None:
    read = _accepted_read()
    bad_chunk = read.chunks[0].model_copy(update={"version": "source-v9"})

    adapted = adapt_external_corpus_result(replace(read, chunks=(bad_chunk,)))

    assert adapted.retrieval is None
    assert adapted.stop_reason is ExternalCorpusStopReason.VERSION_MISMATCH


def test_manifest_checksum_mismatch_stops_before_evidence() -> None:
    read = _accepted_read()
    report = read.corpus_report.model_copy(update={"manifest_sha256": "2" * 64})

    adapted = adapt_external_corpus_result(replace(read, corpus_report=report))

    assert adapted.retrieval is None
    assert adapted.stop_reason is ExternalCorpusStopReason.CHECKSUM_MISMATCH


def test_binding_checksum_mismatch_stops_before_reader() -> None:
    with pytest.raises(ExternalCorpusAdapterError) as error:
        build_controlled_retrieval_request(
            RetrievalRequest(
                turn_target=ObjectScope(store_id="store-a", product_id="product-a"),
                question="battery",
            ),
            binding=_binding(),
            manifest_sha256="2" * 64,
        )

    assert error.value.stop_reason is ExternalCorpusStopReason.CHECKSUM_MISMATCH


def _accepted_read() -> ExternalCorpusReadResult:
    controlled = build_controlled_retrieval_request(
        RetrievalRequest(
            turn_target=ObjectScope(store_id="store-a", product_id="product-a"),
            question="battery",
        ),
        binding=_binding(),
        manifest_sha256=MANIFEST_SHA256,
    )
    candidate = ControlledRetrievalCandidate(
        chunk_id="chunk-a",
        source_id="source-a",
        source_ref="ref-a",
        locator="rag://source-a@source-v1/page/1#ord=0-1",
        product_id="product-a",
        page_number=1,
        ordinal_start=0,
        ordinal_end=1,
        score=1,
        text_sha256="c" * 64,
        token_estimate=4,
    )
    metadata_result = ControlledRetrievalResult(
        request=controlled,
        candidates=(candidate,),
        action_rounds_used=1,
        retrieval_tokens_used=4,
        filtered_out_count=2,
        metadata_digest="d" * 64,
    )
    return ExternalCorpusReadResult(
        request=controlled,
        chunks=(_chunk(),),
        metadata_result=metadata_result,
        corpus_report=CorpusReadinessReport(
            manifest_path="/tmp/manifest.json",
            manifest_sha256=MANIFEST_SHA256,
            source_count=1,
            page_locator_count=1,
            stop_reason=CorpusReadinessStopReason.CORPUS_NOT_INDEXED,
        ),
        manifest=_manifest(),
        stop_reason=ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED,
    )


def _manifest() -> ChunkBaselineManifest:
    return ChunkBaselineManifest(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        status="APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT",
        corpus_version="v0.1",
        append_only=True,
        corpus_manifest_sha256=MANIFEST_SHA256,
        source_inventory_sha256="2" * 64,
        records=(_record(),),
    )


def _record() -> ChunkBaselineRecord:
    return ChunkBaselineRecord(
        chunk_id="chunk-a",
        source_id="source-a",
        source_ref="ref-a",
        source_version="source-v1",
        corpus_version="v0.1",
        store_id="store-a",
        product_id="product-a",
        language="zh-CN",
        region="China mainland",
        page_number=1,
        ordinal_start=0,
        ordinal_end=1,
        extraction_method="metadata-only fixture",
        text_sha256="c" * 64,
        locator="rag://source-a@source-v1/page/1#ord=0-1",
        token_estimate=4,
        keywords=("battery",),
    )


def _chunk() -> DocumentChunk:
    identity = CorpusManifestIdentity.from_manifest(_manifest())
    return DocumentChunk(
        store_id="store-a",
        product_id="product-a",
        source_id="source-a",
        source_type=DocumentSourceType.MANUAL,
        version="source-v1",
        chunk_id="chunk-a",
        order=0,
        locator=SourceLocator(
            source_id="source-a",
            version="source-v1",
            locator="rag://source-a@source-v1/page/1#ord=0-1",
        ),
        heading_path=("ref-a", "battery"),
        text="battery safety",
        metadata={
            "manifest_identity": identity.index_version,
            "manifest_schema_version": identity.schema_version,
            "manifest_corpus_version": identity.corpus_version,
            "manifest_sha256": identity.manifest_sha256,
        },
    )


def _binding(*, variant_id: str | None = None) -> CorpusScopeBinding:
    return CorpusScopeBinding(
        corpus_store_id="corpus-store-a",
        corpus_product_key="corpus-product-a",
        corpus_variant_key=("corpus-variant-a" if variant_id else None),
        manifest_sha256=MANIFEST_SHA256,
        canonical_scope=ObjectScope(
            store_id="store-a",
            product_id="product-a",
            variant_id=variant_id,
        ),
    )
