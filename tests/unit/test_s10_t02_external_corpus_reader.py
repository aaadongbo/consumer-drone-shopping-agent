"""S10-T02 unit coverage for approved external corpus source-region reads."""

import hashlib
import json
from pathlib import Path

import pytest

from backend.rag import (
    ControlledRetrievalRequest,
    ExternalCorpusReader,
    ExternalCorpusStopReason,
)
from backend.rag.chunk_baseline import (
    EXPECTED_CHUNK_BASELINE_SCHEMA,
    EXPECTED_CHUNK_BASELINE_STATUS,
    ChunkBaselineRecord,
)

pytestmark = pytest.mark.unit


def test_reader_loads_only_validated_scoped_regions(tmp_path: Path) -> None:
    text = "mini battery safety"
    corpus_root, chunk_manifest_path = _write_external_corpus_fixture(tmp_path, text)
    loader = _SyntheticRegionLoader({"mini-c001": text})

    result = ExternalCorpusReader(
        corpus_root=corpus_root,
        region_loader=loader,
    ).retrieve(
        chunk_manifest_path=chunk_manifest_path,
        request=ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Mini 3",
            query="battery",
        ),
    )

    assert result.accepted is True
    assert result.stop_reason is ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED
    assert [chunk.product_id for chunk in result.chunks] == ["DJI Mini 3"]
    assert result.chunks[0].text == text
    assert loader.loaded_chunk_ids == ["mini-c001"]


def test_cross_product_query_rejects_before_source_read(tmp_path: Path) -> None:
    corpus_root, chunk_manifest_path = _write_external_corpus_fixture(
        tmp_path,
        "mini battery safety",
    )
    loader = _SyntheticRegionLoader({"mini-c001": "mini battery safety"})

    result = ExternalCorpusReader(
        corpus_root=corpus_root,
        region_loader=loader,
    ).retrieve(
        chunk_manifest_path=chunk_manifest_path,
        request=ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Air 3",
            query="battery",
        ),
    )

    assert result.chunks == ()
    assert result.stop_reason is ExternalCorpusStopReason.NO_SCOPED_MATCH
    assert loader.loaded_chunk_ids == []


def test_source_text_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    corpus_root, chunk_manifest_path = _write_external_corpus_fixture(
        tmp_path,
        "mini battery safety",
    )

    result = ExternalCorpusReader(
        corpus_root=corpus_root,
        region_loader=_SyntheticRegionLoader({"mini-c001": "changed text"}),
    ).retrieve(
        chunk_manifest_path=chunk_manifest_path,
        request=ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Mini 3",
            query="battery",
        ),
    )

    assert result.chunks == ()
    assert result.stop_reason is ExternalCorpusStopReason.SOURCE_TEXT_CHECKSUM_MISMATCH


def test_safe_metadata_excludes_raw_source_text(tmp_path: Path) -> None:
    text = "mini battery safety"
    corpus_root, chunk_manifest_path = _write_external_corpus_fixture(tmp_path, text)

    result = ExternalCorpusReader(
        corpus_root=corpus_root,
        region_loader=_SyntheticRegionLoader({"mini-c001": text}),
    ).retrieve(
        chunk_manifest_path=chunk_manifest_path,
        request=ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Mini 3",
            query="battery",
        ),
    )

    safe = json.dumps(result.safe_metadata(), sort_keys=True)
    assert text not in safe
    assert "text_sha256" in safe


def test_corpus_manifest_checksum_mismatch_fails_before_read(
    tmp_path: Path,
) -> None:
    corpus_root, chunk_manifest_path = _write_external_corpus_fixture(
        tmp_path,
        "mini battery safety",
        corpus_manifest_sha256="f" * 64,
    )
    loader = _SyntheticRegionLoader({"mini-c001": "mini battery safety"})

    result = ExternalCorpusReader(
        corpus_root=corpus_root,
        region_loader=loader,
    ).retrieve(
        chunk_manifest_path=chunk_manifest_path,
        request=ControlledRetrievalRequest(
            store_id="store-dji-cn",
            product_id="DJI Mini 3",
            query="battery",
        ),
    )

    assert result.stop_reason is ExternalCorpusStopReason.CHECKSUM_MISMATCH
    assert loader.loaded_chunk_ids == []


class _SyntheticRegionLoader:
    def __init__(self, text_by_chunk_id: dict[str, str]) -> None:
        self._text_by_chunk_id = text_by_chunk_id
        self.loaded_chunk_ids: list[str] = []

    def load_region(self, record: ChunkBaselineRecord) -> str:
        self.loaded_chunk_ids.append(record.chunk_id)
        return self._text_by_chunk_id[record.chunk_id]


def _write_external_corpus_fixture(
    tmp_path: Path,
    text: str,
    *,
    corpus_manifest_sha256: str | None = None,
) -> tuple[Path, Path]:
    corpus_root = tmp_path / "corpus"
    source_root = corpus_root / "sources"
    locator_root = corpus_root / "derived" / "page_locators"
    source_root.mkdir(parents=True)
    locator_root.mkdir(parents=True)

    source_path = source_root / "mini.pdf"
    source_path.write_bytes(b"%PDF fixture placeholder")
    source_sha = _sha256_file(source_path)
    locator_path = locator_root / "mini.jsonl"
    locator_path.write_text(
        json.dumps(
            {
                "record_type": "ordered_page_locator",
                "source_sha256": source_sha,
                "language": "zh-CN",
                "region": "China mainland",
                "product_scope": "DJI Mini 3",
                "ordinal": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    locator_sha = _sha256_file(locator_path)

    inventory_path = corpus_root / "source_inventory.json"
    _write_json(
        inventory_path,
        {
            "schema_version": "rag-corpus-source-inventory-v0.1",
            "corpus_version": "v0.1",
            "records": [
                {
                    "path": "sources/mini.pdf",
                    "source_id": "official-manual-mini-3",
                    "sha256": source_sha,
                    "pages": 1,
                    "language": "zh-CN",
                    "region": "China mainland",
                    "locator_path": "derived/page_locators/mini.jsonl",
                    "product_scope": "DJI Mini 3",
                }
            ],
        },
    )
    inventory_sha = _sha256_file(inventory_path)

    bindings_root = tmp_path / "bindings"
    bindings_root.mkdir()
    _write_json(
        bindings_root / "human.json",
        {
            "schema_version": "human-review-rag-source-official-verification-v0.3",
            "status": "HUMAN_DECISION_ACCEPTED__RAG_ADMISSION_ALLOWED",
            "approved_scope": _decision_scope(),
        },
    )
    _write_json(
        bindings_root / "copyright.json",
        {
            "schema_version": "copyright-policy-gate-v0.3",
            "status": "HUMAN_DECISION_RAG_ADMISSION_ALLOWED",
            "scope": _decision_scope(),
        },
    )
    _write_json(
        bindings_root / "staging.json",
        {
            "schema_version": "authorized-source-staging-manifest-v0.1",
            "status": "AUTHORIZED_RAW_CANDIDATES__EXTRACTION_NOT_STARTED",
        },
    )

    manifest_path = corpus_root / "manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "rag-corpus-manifest-v0.1",
            "corpus_version": "v0.1",
            "status": "ADMITTED_SOURCE_CORPUS__LOCATORS_INCLUDED__NOT_INDEXED",
            "immutable": True,
            "decision_bindings": {
                "human_review": "../bindings/human.json",
                "copyright_policy": "../bindings/copyright.json",
                "source_staging": "../bindings/staging.json",
            },
            "scope": _decision_scope(),
            "source_files": {
                "sources/mini.pdf": {
                    "sha256": source_sha,
                    "pages": 1,
                    "source_ref": "official-manual-mini-3",
                }
            },
            "derived_files": {
                "derived/page_locators/mini.jsonl": {
                    "sha256": locator_sha,
                    "records": 1,
                }
            },
            "counts": {
                "documents": 1,
                "page_locator_records": 1,
                "chunks": 0,
                "embeddings": 0,
                "indexes": 0,
                "retrieval_runs": 0,
            },
        },
    )
    chunk_manifest_path = tmp_path / "corrected-chunks.manifest.json"
    _write_json(
        chunk_manifest_path,
        {
            "schema_version": EXPECTED_CHUNK_BASELINE_SCHEMA,
            "status": EXPECTED_CHUNK_BASELINE_STATUS,
            "corpus_version": "v0.1",
            "append_only": True,
            "corpus_manifest_sha256": (
                corpus_manifest_sha256 or _sha256_file(manifest_path)
            ),
            "source_inventory_sha256": inventory_sha,
            "records": [
                {
                    "chunk_id": "mini-c001",
                    "source_id": "dji-mini-3-manual-zh-cn-v1.2",
                    "source_ref": "official-manual-mini-3",
                    "source_version": "v1.2",
                    "corpus_version": "v0.1",
                    "store_id": "store-dji-cn",
                    "product_id": "DJI Mini 3",
                    "language": "zh-CN",
                    "region": "China mainland",
                    "page_number": 1,
                    "ordinal_start": 1,
                    "ordinal_end": 1,
                    "extraction_method": "synthetic page fixture",
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "locator": (
                        "rag://dji-mini-3-manual-zh-cn-v1.2@v1.2/page/1#ord=1-1"
                    ),
                    "token_estimate": 3,
                    "keywords": ["battery"],
                }
            ],
        },
    )
    return corpus_root, chunk_manifest_path


def _decision_scope() -> dict[str, object]:
    return {
        "products": ["DJI Mini 3", "DJI Air 3", "DJI Mavic 3"],
        "language": "zh-CN",
        "region": "China mainland",
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
