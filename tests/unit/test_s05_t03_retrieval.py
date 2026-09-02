"""S05-T03 unit coverage for metadata-filtered retrieval."""

from pathlib import Path

import pytest

from backend.common import ObjectScope
from backend.rag import (
    DocumentManifest,
    InMemoryProductRetriever,
    RetrievalRequest,
    RetrievalStrategy,
    chunk_manifest,
)

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def load_chunks():
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    return chunk_manifest(manifest)


def request(question: str, *, product_id: str = "drone-travel") -> RetrievalRequest:
    return RetrievalRequest(
        turn_target=ObjectScope(store_id="store-s02-alpha", product_id=product_id),
        question=question,
        k=2,
    )


def test_retrieval_returns_scoped_ranked_chunks_for_known_question() -> None:
    result = InMemoryProductRetriever(
        load_chunks(), index_version="docs-2026-09-01"
    ).retrieve(request("What is in the package list?"))

    assert result.retrieval_strategy is RetrievalStrategy.KEYWORD_OVERLAP
    assert result.index_version == "docs-2026-09-01"
    assert result.evidence
    assert result.evidence[0].source_id == "drone-travel-package-list"
    assert result.missing_reason is None


def test_retrieval_applies_metadata_filter_before_ranking() -> None:
    chunks = load_chunks()
    foreign = chunks[0].model_copy(update={"product_id": "drone-cinema", "order": -1})
    result = InMemoryProductRetriever(
        (foreign, *chunks), index_version="docs-2026-09-01"
    ).retrieve(request("beginner flight modes"))

    assert result.filtered_out_count == 1
    assert all(chunk.product_id == "drone-travel" for chunk in result.evidence)
    assert foreign not in result.evidence


def test_wrong_product_target_returns_no_cross_product_evidence() -> None:
    result = InMemoryProductRetriever(
        load_chunks(), index_version="docs-2026-09-01"
    ).retrieve(request("battery package list", product_id="drone-cinema"))

    assert result.evidence == ()
    assert result.missing_reason == "NO_SCOPED_MATCH"


def test_variant_target_accepts_product_shared_chunks_without_mutating_scope() -> None:
    result = InMemoryProductRetriever(
        load_chunks(), index_version="docs-2026-09-01"
    ).retrieve(
        RetrievalRequest(
            turn_target=ObjectScope(
                store_id="store-s02-alpha",
                product_id="drone-travel",
                variant_id="travel-pack",
            ),
            question="care policy",
        )
    )

    assert result.evidence
    assert all(chunk.variant_id is None for chunk in result.evidence)
    assert result.request.turn_target.variant_id == "travel-pack"
