"""S09-T01 coverage for corrected chunk-baseline manifest validation."""

import json
from pathlib import Path

import pytest

from backend.rag import (
    EXPECTED_CHUNK_BASELINE_SCHEMA,
    EXPECTED_CHUNK_BASELINE_STATUS,
    ChunkBaselineStopReason,
    validate_corrected_chunk_baseline_manifest,
)

pytestmark = pytest.mark.unit


def test_valid_corrected_chunk_manifest_is_metadata_only(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)

    report = validate_corrected_chunk_baseline_manifest(manifest_path)

    assert report.accepted is True
    assert report.chunk_count == 3
    assert report.stop_reason is ChunkBaselineStopReason.CHUNK_BASELINE_ACCEPTED
    assert report.manifest is not None
    assert "text" not in report.manifest.records[0].model_dump()


def test_missing_chunk_manifest_fails_closed(tmp_path: Path) -> None:
    report = validate_corrected_chunk_baseline_manifest(tmp_path / "missing.json")

    assert report.accepted is False
    assert report.stop_reason is ChunkBaselineStopReason.CHUNK_BASELINE_REQUIRED
    assert report.reasons == ("manifest missing",)


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"status": "DRAFT"}, ChunkBaselineStopReason.CHUNK_BASELINE_INVALID),
        ({"append_only": False}, ChunkBaselineStopReason.CHUNK_BASELINE_INVALID),
        ({"corpus_version": "v9"}, ChunkBaselineStopReason.CHUNK_BASELINE_INVALID),
    ],
)
def test_invalid_manifest_shape_fails_closed(
    tmp_path: Path,
    update: dict[str, object],
    reason: ChunkBaselineStopReason,
) -> None:
    manifest_path = _write_manifest(tmp_path, updates=update)

    report = validate_corrected_chunk_baseline_manifest(manifest_path)

    assert report.accepted is False
    assert report.stop_reason is reason


def test_missing_extraction_ordinal_fields_fail_closed(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["records"][0]["ordinal_start"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_corrected_chunk_baseline_manifest(manifest_path)

    assert report.accepted is False
    assert report.stop_reason is ChunkBaselineStopReason.CHUNK_BASELINE_INVALID


def test_cross_scope_record_fails_closed(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"][0]["language"] = "en-US"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_corrected_chunk_baseline_manifest(manifest_path)

    assert report.accepted is False
    assert report.stop_reason is ChunkBaselineStopReason.SCOPE_MISMATCH


def _write_manifest(
    tmp_path: Path,
    *,
    updates: dict[str, object] | None = None,
) -> Path:
    manifest = {
        "schema_version": EXPECTED_CHUNK_BASELINE_SCHEMA,
        "status": EXPECTED_CHUNK_BASELINE_STATUS,
        "corpus_version": "v0.1",
        "append_only": True,
        "corpus_manifest_sha256": "1" * 64,
        "source_inventory_sha256": "2" * 64,
        "records": [
            _record("mini-c001", "dji-mini-3-manual-zh-cn-v1.2", "DJI Mini 3", 1),
            _record("air-c001", "dji-air-3-manual-zh-cn-v1.6", "DJI Air 3", 2),
            _record("mavic-c001", "dji-mavic-3-manual-zh-cn-v2.3", "DJI Mavic 3", 3),
        ],
    }
    if updates:
        manifest.update(updates)
    manifest_path = tmp_path / "corrected-chunks.manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path


def _record(chunk_id: str, source_id: str, product_id: str, page_number: int) -> dict:
    version = source_id.rsplit("-", 1)[-1]
    return {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "source_ref": f"official-manual-{product_id.casefold().replace(' ', '-')}",
        "source_version": version,
        "corpus_version": "v0.1",
        "store_id": "store-dji-cn",
        "product_id": product_id,
        "language": "zh-CN",
        "region": "China mainland",
        "page_number": page_number,
        "ordinal_start": 0,
        "ordinal_end": 4,
        "extraction_method": "reviewed_page_locator",
        "text_sha256": "a" * 64,
        "locator": f"rag://{source_id}@{version}/page/{page_number}#ord=0-4",
        "token_estimate": 32,
        "keywords": [product_id, "flight", "battery"],
    }
