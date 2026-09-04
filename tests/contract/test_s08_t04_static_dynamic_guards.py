"""S08-T04 contract coverage for static/dynamic and stale-data guards."""

import pytest

from backend.common import ObjectScope
from backend.rag import (
    APPROVED_CHUNK_BASELINE_STATUS,
    DYNAMIC_FACT_REQUIRED,
    SHOPIFY_CANDIDATE_STATUS,
    SHOPIFY_VARIANT_UNRESOLVED_STATUS,
    ChunkBaselineState,
    LocatorBindingSource,
    OfflineLocatorRecord,
    OfflineMetadataLocatorRetriever,
    RetrievalRequest,
    ShopifyCandidateSnapshotState,
    StaticRagPreflightRequest,
    StaticRagStopReason,
    evaluate_static_rag_preflight,
)

pytestmark = pytest.mark.contract


def test_dynamic_commerce_question_never_returns_static_rag_locator() -> None:
    result = OfflineMetadataLocatorRetriever(
        (_locator_record(),),
        index_version="metadata-locators-v0.1",
    ).retrieve(
        RetrievalRequest(
            turn_target=ObjectScope(
                store_id="store-s08-metadata",
                product_id="DJI Mini 3",
            ),
            question="What is the current price and inventory?",
        )
    )

    assert result.candidate_locators == ()
    assert result.missing_reason == DYNAMIC_FACT_REQUIRED


def test_shopify_candidate_snapshot_cannot_be_used_as_current_truth() -> None:
    report = evaluate_static_rag_preflight(
        StaticRagPreflightRequest(
            question="mini battery manual page",
            shopify_snapshot=ShopifyCandidateSnapshotState(
                status=SHOPIFY_CANDIDATE_STATUS,
                variant_id_status=SHOPIFY_VARIANT_UNRESOLVED_STATUS,
                used_as_current_truth=True,
            ),
        )
    )

    assert report.accepted is False
    assert report.stop_reason is StaticRagStopReason.SHOPIFY_CANDIDATE_LIMITATION


@pytest.mark.parametrize(
    ("chunk_baseline", "reason"),
    [
        (
            ChunkBaselineState(manifest_present=False),
            StaticRagStopReason.CHUNK_BASELINE_MANIFEST_MISSING,
        ),
        (
            ChunkBaselineState(
                manifest_present=True,
                review_status="AI_REVIEW_NEEDS_CHANGES",
            ),
            StaticRagStopReason.CHUNK_BASELINE_NEEDS_CHANGES,
        ),
    ],
)
def test_chunk_baseline_must_exist_and_be_approved(
    chunk_baseline: ChunkBaselineState,
    reason: StaticRagStopReason,
) -> None:
    report = evaluate_static_rag_preflight(
        StaticRagPreflightRequest(
            question="mini propeller manual page",
            chunk_baseline=chunk_baseline,
        )
    )

    assert report.accepted is False
    assert report.stop_reason is reason


def test_unfrozen_golden_set_cannot_support_production_metric_claim() -> None:
    report = evaluate_static_rag_preflight(
        StaticRagPreflightRequest(
            question="mini manual metric",
            golden_set_frozen=False,
        )
    )

    assert report.accepted is False
    assert report.stop_reason is StaticRagStopReason.GOLDEN_SET_NOT_FROZEN


def test_training_request_is_rejected_even_when_metadata_is_valid() -> None:
    report = evaluate_static_rag_preflight(
        StaticRagPreflightRequest(
            question="mini manual metadata",
            training_requested=True,
        )
    )

    assert report.accepted is False
    assert report.stop_reason is StaticRagStopReason.TRAINING_NOT_AUTHORIZED


def test_corpus_version_mismatch_stops_static_rag() -> None:
    report = evaluate_static_rag_preflight(
        StaticRagPreflightRequest(
            question="mini manual metadata",
            corpus_version="v0.0",
            expected_corpus_version="v0.1",
        )
    )

    assert report.accepted is False
    assert report.stop_reason is StaticRagStopReason.CORPUS_VERSION_MISMATCH


def test_static_preflight_accepts_only_non_dynamic_current_metadata() -> None:
    report = evaluate_static_rag_preflight(
        StaticRagPreflightRequest(
            question="mini propeller manual page",
            chunk_baseline=ChunkBaselineState(
                manifest_present=True,
                review_status=APPROVED_CHUNK_BASELINE_STATUS,
            ),
            shopify_snapshot=ShopifyCandidateSnapshotState(
                status=SHOPIFY_CANDIDATE_STATUS,
                variant_id_status=SHOPIFY_VARIANT_UNRESOLVED_STATUS,
                used_as_current_truth=False,
            ),
            golden_set_frozen=True,
            training_requested=False,
        )
    )

    assert report.accepted is True
    assert report.stop_reason is None


def _locator_record() -> OfflineLocatorRecord:
    source = LocatorBindingSource(
        source_ref="official-manual-mini-3-zh-cn-v1.2-20260423",
        source_id="dji-mini-3-manual-zh-cn-v1.2",
        version="v1.2",
        checksum="64f06971c787592f2731dca47de9cb4ead811371427cb09b60ff074c0a4e3fea",
        pages=66,
        product_scope="DJI Mini 3 only",
    )
    return OfflineLocatorRecord(
        record={
            "record_type": "ordered_page_locator",
            "source_ref": source.source_ref,
            "source_id": source.source_id,
            "source_sha256": source.checksum,
            "product_scope": source.product_scope,
            "language": source.language,
            "region": source.region,
            "document_version": source.version,
            "page_number": 12,
            "locator": "rag://dji-mini-3-manual-zh-cn-v1.2@v1.2/page/12",
        },
        source=source,
        keywords=("mini", "battery", "manual"),
    )
