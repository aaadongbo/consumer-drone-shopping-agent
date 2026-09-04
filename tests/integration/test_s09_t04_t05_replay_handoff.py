"""S09-T04/T05 development replay and readiness handoff coverage."""

import pytest

from backend.evaluation import (
    S09_MATRIX_IDS,
    DevelopmentReplayCase,
    S09HandoffDecision,
    build_s09_readiness_handoff,
    replay_development_cases,
)
from backend.rag import (
    ChunkBaselineManifest,
    ChunkBaselineRecord,
    ControlledRetrievalRequest,
)

pytestmark = pytest.mark.integration


def test_development_replay_is_non_frozen_and_bounded() -> None:
    report = replay_development_cases(
        _manifest(),
        (
            DevelopmentReplayCase(
                case_id="dev-mini-battery",
                request=ControlledRetrievalRequest(
                    store_id="store-dji-cn",
                    product_id="DJI Mini 3",
                    query="mini battery",
                ),
                expected_locator="rag://dji-mini-3-manual-v1@v1/page/1#ord=0-8",
            ),
        ),
    )

    assert report.development_only is True
    assert report.golden_set_frozen is False
    assert report.case_count == 1
    assert report.passed_count == 1


def test_development_replay_rejects_more_than_fifteen_cases() -> None:
    cases = tuple(
        DevelopmentReplayCase(
            case_id=f"dev-{index}",
            request=ControlledRetrievalRequest(
                store_id="store-dji-cn",
                product_id="DJI Mini 3",
                query="mini battery",
            ),
        )
        for index in range(16)
    )

    with pytest.raises(ValueError, match="limited to 15 cases"):
        replay_development_cases(_manifest(), cases)


def test_handoff_can_go_only_with_complete_metadata_evidence() -> None:
    replay = replay_development_cases(
        _manifest(),
        (
            DevelopmentReplayCase(
                case_id="dev-mini-battery",
                request=ControlledRetrievalRequest(
                    store_id="store-dji-cn",
                    product_id="DJI Mini 3",
                    query="mini battery",
                ),
                expected_locator="rag://dji-mini-3-manual-v1@v1/page/1#ord=0-8",
            ),
        ),
    )

    handoff = build_s09_readiness_handoff(
        chunk_baseline_accepted=True,
        replay_report=replay,
        data_boundary_accepted=True,
        matrix_ids=S09_MATRIX_IDS,
    )

    assert handoff.decision is S09HandoffDecision.GO
    assert handoff.claims_production_ready is False
    assert "PRODUCTION_INDEX" in handoff.deferred_capabilities


def test_handoff_holds_when_chunk_baseline_is_missing() -> None:
    replay = replay_development_cases(_manifest(), ())

    handoff = build_s09_readiness_handoff(
        chunk_baseline_accepted=False,
        replay_report=replay,
        data_boundary_accepted=True,
        matrix_ids=S09_MATRIX_IDS,
    )

    assert handoff.decision is S09HandoffDecision.HOLD
    assert handoff.reason == "readiness evidence incomplete"


def _manifest() -> ChunkBaselineManifest:
    return ChunkBaselineManifest(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        status="APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT",
        corpus_version="v0.1",
        append_only=True,
        corpus_manifest_sha256="1" * 64,
        source_inventory_sha256="2" * 64,
        records=(
            ChunkBaselineRecord(
                chunk_id="mini-c001",
                source_id="dji-mini-3-manual-v1",
                source_ref="official-mini",
                source_version="v1",
                corpus_version="v0.1",
                store_id="store-dji-cn",
                product_id="DJI Mini 3",
                language="zh-CN",
                region="China mainland",
                page_number=1,
                ordinal_start=0,
                ordinal_end=8,
                extraction_method="reviewed_page_locator",
                text_sha256="c" * 64,
                locator="rag://dji-mini-3-manual-v1@v1/page/1#ord=0-8",
                token_estimate=32,
                keywords=("mini", "battery"),
            ),
        ),
    )
