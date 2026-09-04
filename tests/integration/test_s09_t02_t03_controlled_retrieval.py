"""S09-T02/T03 controlled metadata experiment coverage."""

import pytest

from backend.rag import (
    ChunkBaselineManifest,
    ChunkBaselineRecord,
    ChunkBaselineStopReason,
    ControlledRetrievalRequest,
    retrieve_controlled_chunk_metadata,
    run_ephemeral_chunk_metadata_experiment,
)

pytestmark = pytest.mark.integration


def test_ephemeral_metadata_experiment_replays_identically() -> None:
    manifest = _manifest()

    first = run_ephemeral_chunk_metadata_experiment(manifest)
    second = run_ephemeral_chunk_metadata_experiment(manifest)

    assert first == second
    assert first.accepted is True
    assert first.persisted_to_repository is False
    assert first.chunk_count == 3


def test_scoped_retrieval_returns_only_turn_target_locators() -> None:
    result = retrieve_controlled_chunk_metadata(
        _manifest(),
        ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Mini 3",
            query="mini battery",
            field_hint="battery",
        ),
    )

    assert result.stop_reason is None
    assert [candidate.product_id for candidate in result.candidates] == ["DJI Mini 3"]
    assert result.candidates[0].locator.startswith("rag://dji-mini-3")


def test_cross_product_match_is_rejected_before_scoring() -> None:
    result = retrieve_controlled_chunk_metadata(
        _manifest(),
        ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Air 3",
            query="mini battery",
            field_hint="battery",
        ),
    )

    assert result.candidates == ()
    assert result.stop_reason is ChunkBaselineStopReason.NO_SCOPED_MATCH


def test_retrieval_token_budget_fails_closed_without_partial_candidates() -> None:
    result = retrieve_controlled_chunk_metadata(
        _manifest(token_estimate=2500),
        ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Mini 3",
            query="mini battery",
            max_retrieval_tokens=100,
        ),
    )

    assert result.candidates == ()
    assert result.stop_reason is ChunkBaselineStopReason.RETRIEVAL_TOKEN_BUDGET
    assert result.retrieval_tokens_used > 100


def test_candidate_limit_fails_closed() -> None:
    manifest = ChunkBaselineManifest(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        status="APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT",
        corpus_version="v0.1",
        append_only=True,
        corpus_manifest_sha256="1" * 64,
        source_inventory_sha256="2" * 64,
        records=tuple(
            _record(f"mini-c{index:03d}", "DJI Mini 3", "mini battery", index)
            for index in range(1, 12)
        ),
    )

    result = retrieve_controlled_chunk_metadata(
        manifest,
        ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Mini 3",
            query="mini battery",
        ),
    )

    assert result.candidates == ()
    assert result.stop_reason is ChunkBaselineStopReason.SCOPED_CANDIDATE_LIMIT


def _manifest(*, token_estimate: int = 32) -> ChunkBaselineManifest:
    return ChunkBaselineManifest(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        status="APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT",
        corpus_version="v0.1",
        append_only=True,
        corpus_manifest_sha256="1" * 64,
        source_inventory_sha256="2" * 64,
        records=(
            _record("mini-c001", "DJI Mini 3", "mini battery", 1, token_estimate),
            _record("air-c001", "DJI Air 3", "air obstacle", 2, token_estimate),
            _record("mavic-c001", "DJI Mavic 3", "mavic firmware", 3, token_estimate),
        ),
    )


def _record(
    chunk_id: str,
    product_id: str,
    keywords: str,
    page_number: int,
    token_estimate: int = 32,
) -> ChunkBaselineRecord:
    source_id = product_id.casefold().replace(" ", "-") + "-manual-v1"
    return ChunkBaselineRecord(
        chunk_id=chunk_id,
        source_id=source_id,
        source_ref=f"official-{source_id}",
        source_version="v1",
        corpus_version="v0.1",
        store_id="store-dji-cn",
        product_id=product_id,
        language="zh-CN",
        region="China mainland",
        page_number=page_number,
        ordinal_start=0,
        ordinal_end=8,
        extraction_method="reviewed_page_locator",
        text_sha256="b" * 64,
        locator=f"rag://{source_id}@v1/page/{page_number}#ord=0-8",
        token_estimate=token_estimate,
        keywords=tuple(keywords.split()),
    )
