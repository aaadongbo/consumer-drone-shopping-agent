"""S08-T03 integration coverage for offline metadata-only retrieval."""

import pytest

from backend.common import ObjectScope
from backend.rag import (
    CORPUS_NOT_INDEXED,
    NO_SCOPED_MATCH,
    SCOPED_CANDIDATE_LIMIT,
    LocatorBindingSource,
    Mavic3ScopeOverlay,
    OfflineLocatorRecord,
    OfflineMetadataLocatorRetriever,
    RetrievalRequest,
    RetrievalStrategy,
)

pytestmark = pytest.mark.integration


MINI_SHA256 = "64f06971c787592f2731dca47de9cb4ead811371427cb09b60ff074c0a4e3fea"
AIR_SHA256 = "f6134ef3bd41cefd226bc56b40b376d86b348c60489c4006472364d5d2fbfd23"
MAVIC_SHA256 = "f5a6d4148726450cdb0b72de1598d31a2ea478a044182d4b8da4941d935070fa"


@pytest.mark.parametrize(
    ("product_id", "question", "expected_source_id"),
    [
        ("DJI Mini 3", "mini battery charging", "dji-mini-3-manual-zh-cn-v1.2"),
        ("DJI Air 3", "air obstacle sensing", "dji-air-3-manual-zh-cn-v1.6"),
        ("DJI Mavic 3", "mavic firmware update", "dji-mavic-3-manual-zh-cn-v2.3"),
    ],
)
def test_single_target_returns_same_product_locator_candidates(
    product_id: str,
    question: str,
    expected_source_id: str,
) -> None:
    result = _retriever().retrieve(_request(product_id, question))

    assert result.retrieval_strategy is RetrievalStrategy.KEYWORD_OVERLAP
    assert result.missing_reason is None
    assert [binding.source_id for binding in result.candidate_locators] == [
        expected_source_id
    ]
    assert all(
        product_id in binding.product_scope for binding in result.candidate_locators
    )


def test_cross_product_candidate_is_rejected_before_ranking() -> None:
    result = _retriever().retrieve(_request("DJI Air 3", "mini battery charging", k=3))

    assert result.candidate_locators == ()
    assert result.missing_reason == NO_SCOPED_MATCH
    assert result.filtered_out_count == 4


def test_budget_limit_stops_without_returning_partial_candidates() -> None:
    records = tuple(
        _locator_record(
            _mini_source(),
            page_number=page_number,
            keywords=("mini", "battery"),
        )
        for page_number in range(1, 12)
    )
    result = OfflineMetadataLocatorRetriever(
        records,
        index_version="metadata-locators-v0.1",
        max_scoped_candidates=10,
    ).retrieve(_request("DJI Mini 3", "mini battery", k=10))

    assert result.candidate_locators == ()
    assert result.missing_reason == SCOPED_CANDIDATE_LIMIT


def test_not_indexed_empty_corpus_reports_exact_stop_reason() -> None:
    result = OfflineMetadataLocatorRetriever(
        (),
        index_version="metadata-locators-v0.1",
        corpus_indexed=False,
    ).retrieve(_request("DJI Mini 3", "mini battery"))

    assert result.candidate_locators == ()
    assert result.missing_reason == CORPUS_NOT_INDEXED


def test_deterministic_replay_is_stable() -> None:
    retriever = _retriever()
    request = _request("DJI Mavic 3", "mavic firmware update")

    first = retriever.retrieve(request).model_dump_json()
    second = retriever.retrieve(request).model_dump_json()

    assert first == second


def _request(product_id: str, question: str, *, k: int = 2) -> RetrievalRequest:
    return RetrievalRequest(
        turn_target=ObjectScope(store_id="store-s08-metadata", product_id=product_id),
        question=question,
        k=k,
    )


def _retriever() -> OfflineMetadataLocatorRetriever:
    return OfflineMetadataLocatorRetriever(
        (
            _locator_record(
                _mini_source(),
                page_number=12,
                keywords=("mini", "battery", "charging"),
            ),
            _locator_record(
                _air_source(),
                page_number=21,
                keywords=("air", "obstacle", "sensing"),
            ),
            _locator_record(
                _mavic_source(),
                page_number=5,
                keywords=("mavic", "firmware", "update"),
            ),
            _locator_record(
                _mavic_source(),
                page_number=3,
                keywords=("mavic", "cine", "camera"),
            ),
        ),
        index_version="metadata-locators-v0.1",
        overlays=(
            Mavic3ScopeOverlay(
                source_id="dji-mavic-3-manual-zh-cn-v2.3",
                excluded_pages=(3,),
            ),
        ),
    )


def _mini_source() -> LocatorBindingSource:
    return LocatorBindingSource(
        source_ref="official-manual-mini-3-zh-cn-v1.2-20260423",
        source_id="dji-mini-3-manual-zh-cn-v1.2",
        version="v1.2",
        checksum=MINI_SHA256,
        pages=66,
        product_scope="DJI Mini 3 only",
    )


def _air_source() -> LocatorBindingSource:
    return LocatorBindingSource(
        source_ref="official-manual-air-3-zh-cn-v1.6-20240627",
        source_id="dji-air-3-manual-zh-cn-v1.6",
        version="v1.6",
        checksum=AIR_SHA256,
        pages=109,
        product_scope="DJI Air 3 only",
    )


def _mavic_source() -> LocatorBindingSource:
    return LocatorBindingSource(
        source_ref="official-manual-mavic-3-zh-cn-v2.3-20240606",
        source_id="dji-mavic-3-manual-zh-cn-v2.3",
        version="v2.3",
        checksum=MAVIC_SHA256,
        pages=86,
        product_scope="DJI Mavic 3 only; Cine excluded by overlay",
    )


def _locator_record(
    source: LocatorBindingSource,
    *,
    page_number: int,
    keywords: tuple[str, ...],
) -> OfflineLocatorRecord:
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
            "page_number": page_number,
            "locator": f"rag://{source.source_id}@{source.version}/page/{page_number}",
        },
        source=source,
        keywords=keywords,
    )
