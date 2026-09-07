"""Validation tests for the offline BM25 evaluator ingestion boundary."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from backend.rag.chunk_baseline import ChunkBaselineManifest, ChunkBaselineRecord
from scripts import evaluate_bm25
from scripts.evaluate_bm25 import (
    _benchmark_scope_label,
    _build_documents,
    _scope_for_row,
)

pytestmark = pytest.mark.unit


def _write_fixture(
    tmp_path: Path, *, text: str = "起飞重量"
) -> tuple[Path, Path, ChunkBaselineManifest]:
    locator_dir = tmp_path / "locators"
    locator_dir.mkdir()
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(
        json.dumps(
            {
                "source_id": "source-air-v1",
                "excluded_from_future_mavic_3_retrieval_pending_section_review": [],
            }
        ),
        encoding="utf-8",
    )
    text_sha256 = hashlib.sha256(text.encode()).hexdigest()
    locator = {
        "source_id": "source-air-v1",
        "document_version": "v1",
        "page_number": 1,
        "verbatim_text": text,
        "text_sha256": text_sha256,
    }
    (locator_dir / "source-air-v1.jsonl").write_text(
        json.dumps(locator) + "\n", encoding="utf-8"
    )
    baseline = ChunkBaselineManifest(
        schema_version="rag-corrected-chunk-baseline-v0.1",
        status="APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT",
        corpus_version="v0.1",
        append_only=True,
        corpus_manifest_sha256="a" * 64,
        source_inventory_sha256="b" * 64,
        records=(
            ChunkBaselineRecord(
                chunk_id="source-air-v1-p001-o0001",
                source_id="source-air-v1",
                source_ref="official-air-v1",
                source_version="v1",
                corpus_version="v0.1",
                store_id="bys-user-store-578412-7a11gk0u.myshopify.com",
                product_id="DJI Air 3",
                variant_id=None,
                language="zh-CN",
                region="China mainland",
                page_number=1,
                ordinal_start=1,
                ordinal_end=1,
                extraction_method="pdftotext -layout per-page",
                text_sha256=text_sha256,
                locator="rag://source-air-v1@v1/page/1#ord=1-1",
                token_estimate=0,
                keywords=("DJI Air 3",),
            ),
        ),
    )
    return locator_dir, overlay_path, baseline


def test_ingestion_preserves_baseline_scope_and_provenance(tmp_path: Path) -> None:
    locator_dir, overlay_path, baseline = _write_fixture(tmp_path)

    documents = _build_documents(locator_dir, overlay_path, baseline)

    assert len(documents) == 1
    assert documents[0].product_id == "9278460821642"
    assert documents[0].variant_id is None
    assert documents[0].locator.endswith("#ord=1-1")


def test_ingestion_rejects_locator_checksum_mismatch(tmp_path: Path) -> None:
    locator_dir, overlay_path, baseline = _write_fixture(tmp_path)
    locator_path = locator_dir / "source-air-v1.jsonl"
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    locator["verbatim_text"] = "被篡改"
    locator_path.write_text(json.dumps(locator) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="text checksum mismatch"):
        _build_documents(locator_dir, overlay_path, baseline)


def test_scope_conversion_preserves_exact_variant_identity() -> None:
    scope = _scope_for_row(
        {
            "store_id": "shopify-store:bys-user-store-578412-7a11gk0u",
            "product_id": "9278460821642",
            "variant_id": "50107426603146",
            "product_scope": "DJI Air 3",
        }
    )
    assert scope is not None
    assert scope.variant_id == "50107426603146"
    assert _scope_for_row({**scope.model_dump(), "variant_id": "wrong"}) is None


def test_multi_product_scope_is_rejected_even_when_product_id_is_present() -> None:
    row = {
        "store_id": "shopify-store:bys-user-store-578412-7a11gk0u",
        "product_id": "9278439686282",
        "variant_id": None,
        "product_scope": "DJI Mini 3, DJI Air 3, DJI Mavic 3",
    }

    assert _benchmark_scope_label(row) == "multi_product"
    assert _scope_for_row(row) is None


def test_cli_writes_metadata_only_and_refuses_nonempty_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        evaluate_bm25,
        "evaluate",
        lambda *args: {
            "status": "EXECUTED_OFFLINE_METADATA_ONLY",
            "per_query": [{"query_id": "q1", "query_text_hash": "sha256:" + "a" * 64}],
            "corpus": {"index_version": "v0.1:test", "document_count": 1},
            "metrics": {
                "answerable_count": 0,
                "evidence_recall_at_10": None,
                "scope_leakage_count": 0,
            },
            "method": {"shopify_reads": 0, "shopify_writes": 0},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_bm25.py",
            "--golden-dir",
            str(tmp_path),
            "--locator-dir",
            str(tmp_path),
            "--overlay",
            str(tmp_path / "overlay.json"),
            "--chunk-manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(output_dir),
        ],
    )
    assert evaluate_bm25.main() == 0
    report_text = (output_dir / "evaluation_report.json").read_text(encoding="utf-8")
    assert '"query_text":' not in report_text
    with pytest.raises(SystemExit, match="append-only refusal"):
        evaluate_bm25.main()
