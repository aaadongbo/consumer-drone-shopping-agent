"""Unit coverage for the internal BM25 baseline."""

import pytest

from backend.common import ObjectScope
from backend.rag.bm25 import (
    Bm25Document,
    Bm25Index,
    Bm25Request,
    Bm25StopReason,
    tokenize_bm25,
)

pytestmark = pytest.mark.unit


def _document(
    document_id: str,
    text: str,
    *,
    product_id: str = "mini",
    variant_id: str | None = None,
    page: int = 1,
    token_estimate: int = 12,
    store_id: str = "store",
) -> Bm25Document:
    import hashlib

    return Bm25Document(
        document_id=document_id,
        text=text,
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        source_id=f"source-{document_id}",
        source_version="v1",
        locator=f"rag://source-{document_id}@v1/page/{page}#p={page}",
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        page_number=page,
        token_estimate=token_estimate,
    )


def _request(query: str, *, variant_id: str | None = None, **kwargs) -> Bm25Request:
    return Bm25Request(
        turn_target=ObjectScope(
            store_id="store",
            product_id="mini",
            variant_id=variant_id,
        ),
        query=query,
        **kwargs,
    )


def test_cjk_tokenizer_is_deterministic_and_includes_bigrams() -> None:
    assert tokenize_bm25("Air 3 避障") == (
        "air",
        "3",
        "避",
        "障",
        "避障",
    )
    assert "起飞" in tokenize_bm25("起飞重量")


def test_scope_filters_before_bm25_and_variant_inherits_shared_documents() -> None:
    shared = _document("shared", "Mini 3 起飞重量", page=2)
    exact = _document("exact", "Mini 3 套装电池", variant_id="v1", page=3)
    foreign = _document("foreign", "Mini 3 起飞重量", product_id="air", page=4)
    result = Bm25Index((shared, exact, foreign), index_version="manifest").search(
        _request("起飞重量", variant_id="v1", k=3)
    )
    assert [candidate.document_id for candidate in result.candidates] == ["shared"]
    assert result.filtered_out_count == 1
    assert result.stop_reason is None


def test_product_request_rejects_variant_specific_documents() -> None:
    result = Bm25Index(
        (_document("variant", "套装电池", variant_id="v1"),),
        index_version="manifest",
    ).search(_request("套装电池"))
    assert result.candidates == ()
    assert result.stop_reason is Bm25StopReason.NO_SCOPED_MATCH


def test_variant_request_rejects_other_variant_and_store() -> None:
    docs = (
        _document("other-variant", "套装电池", variant_id="v2"),
        _document("other-store", "套装电池", store_id="other"),
    )
    result = Bm25Index(docs, index_version="manifest").search(
        _request("套装电池", variant_id="v1")
    )
    assert result.candidates == ()
    assert result.filtered_out_count == 2
    assert result.stop_reason is Bm25StopReason.NO_SCOPED_MATCH


def test_dynamic_commerce_query_fails_closed_before_ranking() -> None:
    result = Bm25Index(
        (_document("price", "Mini 3 价格"),),
        index_version="manifest",
    ).search(_request("Mini 3 多少钱"))
    assert result.candidates == ()
    assert result.stop_reason is Bm25StopReason.DYNAMIC_FACT_REQUIRED


def test_candidate_cap_bounds_results_and_token_budget_fails_closed() -> None:
    docs = tuple(_document(f"doc-{i}", "避障 视觉系统", page=i) for i in range(1, 4))
    index = Bm25Index(docs, index_version="manifest")
    capped = index.search(_request("避障", candidate_cap=2))
    assert capped.stop_reason is Bm25StopReason.SCOPED_CANDIDATE_LIMIT
    assert len(capped.candidates) == 2
    budget = index.search(_request("避障", max_retrieval_tokens=1))
    assert budget.stop_reason is Bm25StopReason.RETRIEVAL_TOKEN_BUDGET


def test_ranking_is_reproducible() -> None:
    docs = (
        _document("a", "Air 3 视觉避障", product_id="air", page=2),
        _document("b", "Air 3 视觉系统与避障限制", product_id="air", page=1),
    )
    request = Bm25Request(
        turn_target=ObjectScope(store_id="store", product_id="air"),
        query="避障限制",
    )
    index = Bm25Index(docs, index_version="manifest")
    assert index.search(request) == index.search(request)
