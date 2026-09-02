"""S05-T02 unit coverage for stable scoped document chunking."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.rag import (
    DocumentChunk,
    DocumentManifest,
    chunk_document_source,
    chunk_manifest,
)

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def load_manifest() -> DocumentManifest:
    return DocumentManifest.model_validate_json(_FIXTURE.read_text(encoding="utf-8"))


def test_chunk_manifest_preserves_scope_source_version_and_order() -> None:
    manifest = load_manifest()
    chunks = chunk_manifest(manifest)

    assert [chunk.order for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.store_id for chunk in chunks} == {manifest.store_id}
    assert {chunk.product_id for chunk in chunks} == {manifest.product_id}
    assert {chunk.variant_id for chunk in chunks} == {None}
    assert {chunk.version for chunk in chunks} == {manifest.document_version}
    assert {chunk.locator.version for chunk in chunks} == {manifest.document_version}
    assert all(manifest.source_by_id(chunk.locator.source_id) for chunk in chunks)


def test_chunking_is_deterministic_and_returns_fresh_values() -> None:
    first = chunk_manifest(load_manifest())
    second = chunk_manifest(load_manifest())

    assert first == second
    assert first is not second
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_heading_boundaries_and_list_rows_keep_locator_context() -> None:
    manifest = load_manifest()
    source = manifest.sources[0].model_copy(
        update={
            "text": "\n".join(
                [
                    "# FAQ",
                    "What modes are supported?",
                    "- Beginner",
                    "- Travel",
                    "",
                    "# Safety",
                    "Check propellers before flight.",
                ]
            )
        }
    )

    chunks = chunk_document_source(source)

    assert len(chunks) == 2
    assert chunks[0].heading_path == ("Northwind Travel FAQ", "FAQ")
    assert chunks[0].text.splitlines() == [
        "What modes are supported?",
        "- Beginner",
        "- Travel",
    ]
    assert chunks[0].locator.locator.endswith("/chunk/000")
    assert chunks[1].heading_path == ("Northwind Travel FAQ", "Safety")
    assert chunks[1].locator.locator.endswith("/chunk/001")


def test_table_like_rows_are_kept_together_until_blank_line() -> None:
    manifest = load_manifest()
    source = manifest.sources[1].model_copy(
        update={
            "text": "\n".join(
                [
                    "# Package List",
                    "| Item | Lite | Pack |",
                    "| Battery | 1 | 3 |",
                    "",
                    "# Notes",
                    "Remote included.",
                ]
            )
        }
    )

    chunks = chunk_document_source(source)

    assert len(chunks) == 2
    assert "| Battery | 1 | 3 |" in chunks[0].text
    assert chunks[0].source_type == source.source_type
    assert chunks[0].metadata["document_version"] == source.version


def test_chunk_locator_must_match_chunk_identity() -> None:
    chunk = chunk_manifest(load_manifest())[0]

    with pytest.raises(ValidationError, match="source_id"):
        DocumentChunk.model_validate(
            {
                **chunk.to_wire(),
                "locator": {
                    "source_id": "other-source",
                    "version": chunk.version,
                    "locator": f"rag://other-source@{chunk.version}/chunk/000",
                },
            }
        )
