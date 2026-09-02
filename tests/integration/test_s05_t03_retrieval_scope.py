"""S05-T03 integration coverage for local Product RAG retrieval fixtures."""

from pathlib import Path

import pytest

from backend.common import ObjectScope
from backend.rag import DocumentManifest, InMemoryProductRetriever, RetrievalRequest
from backend.rag.manifest import chunk_manifest

pytestmark = pytest.mark.integration

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def retriever() -> InMemoryProductRetriever:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    return InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    )


@pytest.mark.parametrize(
    ("question", "expected_source"),
    [
        ("Which beginner flight modes are described?", "drone-travel-faq"),
        ("How many batteries are in the package?", "drone-travel-package-list"),
        ("What should I check before takeoff?", "drone-travel-manual"),
        ("Is care coverage available?", "drone-travel-policy"),
    ],
)
def test_known_static_questions_retrieve_supporting_evidence(
    question: str, expected_source: str
) -> None:
    result = retriever().retrieve(
        RetrievalRequest(
            turn_target=ObjectScope(
                store_id="store-s02-alpha",
                product_id="drone-travel",
            ),
            question=question,
            k=3,
        )
    )

    assert expected_source in {chunk.source_id for chunk in result.evidence}
    assert all(chunk.store_id == "store-s02-alpha" for chunk in result.evidence)
    assert all(chunk.product_id == "drone-travel" for chunk in result.evidence)
