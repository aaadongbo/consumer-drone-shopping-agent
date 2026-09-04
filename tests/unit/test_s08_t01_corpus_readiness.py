"""S08-T01 unit coverage for external corpus readiness metadata."""

import json
from pathlib import Path

import pytest

from backend.rag import (
    CorpusReadinessStopReason,
    build_corpus_readiness_report,
)

pytestmark = pytest.mark.unit

MINI_SHA256 = "64f06971c787592f2731dca47de9cb4ead811371427cb09b60ff074c0a4e3fea"
AIR_SHA256 = "f6134ef3bd41cefd226bc56b40b376d86b348c60489c4006472364d5d2fbfd23"
MAVIC_SHA256 = "f5a6d4148726450cdb0b72de1598d31a2ea478a044182d4b8da4941d935070fa"
VERIFICATION_ROOT = "../rag-source-official-verification-20260901-v0.1"
STAGING_ROOT = "../rag-source-authorized-staging-20260901-v0.1"


def test_valid_admitted_metadata_reports_not_indexed(tmp_path: Path) -> None:
    root = _write_corpus_fixture(tmp_path)

    report = build_corpus_readiness_report(root)

    assert report.metadata_accepted is True
    assert report.corpus_version == "v0.1"
    assert report.source_count == 3
    assert report.page_locator_count == 3
    assert report.counts["chunks"] == 0
    assert report.counts["embeddings"] == 0
    assert report.counts["indexes"] == 0
    assert report.counts["retrieval_runs"] == 0
    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_NOT_INDEXED
    assert report.rejected_files == ()
    assert report.manifest_sha256 is not None


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "outputs" / "rag-corpus-20260902-v0.1"
    root.mkdir(parents=True)

    report = build_corpus_readiness_report(root)

    assert report.metadata_accepted is False
    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_MANIFEST_MISSING
    assert report.manifest_sha256 is None
    assert [item.reason for item in report.rejected_files] == ["manifest missing"]


@pytest.mark.parametrize(
    "relative_path",
    [
        "manifest.json",
        "source_inventory.json",
        "derived/mavic_3_scope_overlay.v0.1.json",
        "../rag-source-official-verification-20260901-v0.1/"
        "human_review.rag-source-official-verification.v0.3.json",
    ],
)
def test_malformed_metadata_json_fails_closed(
    tmp_path: Path,
    relative_path: str,
) -> None:
    root = _write_corpus_fixture(tmp_path)
    target = root / relative_path
    target.write_text("{not-json", encoding="utf-8")
    if relative_path == "derived/mavic_3_scope_overlay.v0.1.json":
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["derived_files"][relative_path]["sha256"] = _sha256_file(target)
        _write_json(manifest_path, manifest)

    report = build_corpus_readiness_report(root)

    assert report.metadata_accepted is False
    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_METADATA_MISMATCH
    assert any("json invalid" in (item.reason or "") for item in report.rejected_files)


def test_locator_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    root = _write_corpus_fixture(tmp_path)
    locator = root / "derived/page_locators/dji-mini-3-manual-zh-cn-v1.2.jsonl"
    locator.write_text(locator.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = build_corpus_readiness_report(root)

    assert report.metadata_accepted is False
    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_CHECKSUM_MISMATCH
    assert any(
        "sha256 mismatch" in (item.reason or "") for item in report.rejected_files
    )


def test_invalid_manifest_status_fails_closed(tmp_path: Path) -> None:
    root = _write_corpus_fixture(tmp_path, manifest_updates={"status": "DRAFT"})

    report = build_corpus_readiness_report(root)

    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_METADATA_MISMATCH
    assert [item.reason for item in report.rejected_files] == [
        "manifest status not admitted"
    ]


def test_nonzero_index_counts_fail_closed(tmp_path: Path) -> None:
    root = _write_corpus_fixture(tmp_path, count_updates={"indexes": 1})

    report = build_corpus_readiness_report(root)

    assert report.metadata_accepted is False
    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_METADATA_MISMATCH
    assert report.rejected_files == ()


def test_decision_binding_status_and_scope_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    root = _write_corpus_fixture(tmp_path)
    human_review = (
        root.parent
        / "rag-source-official-verification-20260901-v0.1"
        / "human_review.rag-source-official-verification.v0.3.json"
    )
    document = json.loads(human_review.read_text(encoding="utf-8"))
    document["status"] = "AI_REVIEW_NEEDS_CHANGES"
    document["approved_scope"]["language"] = "en-US"
    human_review.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    report = build_corpus_readiness_report(root)

    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_METADATA_MISMATCH
    assert {item.reason for item in report.rejected_files} >= {
        "human_review status mismatch",
        "decision language mismatch",
    }


def test_report_is_deterministic(tmp_path: Path) -> None:
    root = _write_corpus_fixture(tmp_path)

    first = build_corpus_readiness_report(root).model_dump_json()
    second = build_corpus_readiness_report(root).model_dump_json()

    assert first == second


def test_readiness_adapter_does_not_open_files_for_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_corpus_fixture(tmp_path)
    opened_modes: list[str] = []
    original_open = Path.open

    def track_open(self: Path, mode: str = "r", *args: object, **kwargs: object):
        opened_modes.append(mode)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", track_open)

    report = build_corpus_readiness_report(root)

    assert report.stop_reason is CorpusReadinessStopReason.CORPUS_NOT_INDEXED
    assert all(not set(mode) & {"w", "a", "x", "+"} for mode in opened_modes)


def _write_corpus_fixture(
    tmp_path: Path,
    *,
    manifest_updates: dict[str, object] | None = None,
    count_updates: dict[str, int | bool] | None = None,
) -> Path:
    root = tmp_path / "outputs" / "rag-corpus-20260902-v0.1"
    locator_root = root / "derived" / "page_locators"
    locator_root.mkdir(parents=True)

    sources = [
        {
            "manifest_path": "sources/DJI_Mini_3_User_Manual_chs_20260423.pdf",
            "source_ref": "official-manual-mini-3-zh-cn-v1.2-20260423",
            "locator_path": "derived/page_locators/dji-mini-3-manual-zh-cn-v1.2.jsonl",
            "locator_source_id": "dji-mini-3-manual-zh-cn-v1.2",
            "product_scope": "DJI Mini 3 only",
            "product_family": "DJI Mini",
            "version": "v1.2",
            "sha256": MINI_SHA256,
            "pages": 1,
        },
        {
            "manifest_path": "sources/DJI_Air_3_User_Manual_v1.6_zh-cn_20240627.pdf",
            "source_ref": "official-manual-air-3-zh-cn-v1.6-20240627",
            "locator_path": "derived/page_locators/dji-air-3-manual-zh-cn-v1.6.jsonl",
            "locator_source_id": "dji-air-3-manual-zh-cn-v1.6",
            "product_scope": "DJI Air 3 only",
            "product_family": "DJI Air",
            "version": "v1.6",
            "sha256": AIR_SHA256,
            "pages": 1,
        },
        {
            "manifest_path": "sources/DJI_Mavic_3_User_Manual_v2.3_CHS_20240723.pdf",
            "source_ref": "official-manual-mavic-3-zh-cn-v2.3-20240606",
            "locator_path": "derived/page_locators/dji-mavic-3-manual-zh-cn-v2.3.jsonl",
            "locator_source_id": "dji-mavic-3-manual-zh-cn-v2.3",
            "product_scope": "DJI Mavic 3 only",
            "product_family": "DJI Mavic",
            "version": "v2.3",
            "sha256": MAVIC_SHA256,
            "pages": 1,
        },
    ]

    locator_metadata: dict[str, dict[str, int | str]] = {}
    for source in sources:
        locator_path = root / str(source["locator_path"])
        _write_jsonl(
            locator_path,
            [
                {
                    "record_type": "ordered_page_locator",
                    "source_id": source["locator_source_id"],
                    "source_sha256": source["sha256"],
                    "product_scope": source["product_scope"],
                    "product_family": source["product_family"],
                    "language": "zh-CN",
                    "region": "China mainland",
                    "document_version": source["version"],
                    "page_number": 1,
                    "page_heading_candidate": "metadata-only fixture",
                    "heading_locator_status": "FIXTURE",
                    "ordinal": 1,
                    "text_sha256": "0" * 64,
                    "extraction_method": "metadata-only fixture",
                    "warnings": [],
                }
            ],
        )
        locator_metadata[str(source["locator_path"])] = {
            "sha256": _sha256_file(locator_path),
            "records": 1,
        }

    overlay_path = root / "derived" / "mavic_3_scope_overlay.v0.1.json"
    _write_json(
        overlay_path,
        {
            "schema_version": "source-scope-overlay-v0.1",
            "source_id": "dji-mavic-3-manual-zh-cn-v2.3",
            "excluded_from_future_mavic_3_retrieval_pending_section_review": [3],
        },
    )

    source_inventory_records = []
    for source in sources:
        record = {
            "source_id": source["source_ref"],
            "product_scope": source["product_scope"],
            "document_type": "user_manual",
            "official_url": "https://example.invalid/metadata-only",
            "language": "zh-CN",
            "region": "China mainland",
            "version_or_date": f"{source['version']}; metadata-only",
            "path": source["manifest_path"],
            "sha256": source["sha256"],
            "pages": source["pages"],
            "locator_path": source["locator_path"],
        }
        if "Mavic" in str(source["product_family"]):
            record["scope_overlay_path"] = "derived/mavic_3_scope_overlay.v0.1.json"
        source_inventory_records.append(record)
    _write_json(
        root / "source_inventory.json",
        {
            "schema_version": "rag-corpus-source-inventory-v0.1",
            "corpus_id": "consumer-drone-rag-corpus",
            "corpus_version": "v0.1",
            "records": source_inventory_records,
        },
    )

    _write_decision_sidecars(root.parent)

    counts: dict[str, int | bool] = {
        "documents": 3,
        "page_locator_records": 3,
        "chunks": 0,
        "embeddings": 0,
        "indexes": 0,
        "retrieval_runs": 0,
        "training_runs": 0,
        "golden_set_frozen": False,
    }
    if count_updates:
        counts.update(count_updates)

    manifest = {
        "schema_version": "rag-corpus-manifest-v0.1",
        "corpus_id": "consumer-drone-rag-corpus",
        "corpus_version": "v0.1",
        "created_at": "2026-09-02T00:01:43Z",
        "status": "ADMITTED_SOURCE_CORPUS__LOCATORS_INCLUDED__NOT_INDEXED",
        "immutable": True,
        "overwrite_policy": "DO_NOT_OVERWRITE",
        "decision_bindings": {
            "human_review": (
                f"{VERIFICATION_ROOT}/"
                "human_review.rag-source-official-verification.v0.3.json"
            ),
            "copyright_policy": (
                f"{VERIFICATION_ROOT}/copyright_policy_gate.v0.3.json"
            ),
            "source_staging": f"{STAGING_ROOT}/manifest.json",
        },
        "scope": {
            "products": ["DJI Mini 3", "DJI Air 3", "DJI Mavic 3"],
            "language": "zh-CN",
            "region": "China mainland",
        },
        "source_files": {
            str(source["manifest_path"]): {
                "sha256": source["sha256"],
                "bytes": 1,
                "pages": source["pages"],
                "source_ref": source["source_ref"],
            }
            for source in sources
        },
        "derived_files": {
            "source_inventory.json": "Source metadata and Product scope bindings.",
            **locator_metadata,
            "derived/mavic_3_scope_overlay.v0.1.json": {
                "sha256": _sha256_file(overlay_path)
            },
        },
        "counts": counts,
    }
    if manifest_updates:
        manifest.update(manifest_updates)
    _write_json(root / "manifest.json", manifest)
    return root


def _write_decision_sidecars(outputs_root: Path) -> None:
    verification_root = outputs_root / "rag-source-official-verification-20260901-v0.1"
    staging_root = outputs_root / "rag-source-authorized-staging-20260901-v0.1"
    _write_json(
        verification_root / "human_review.rag-source-official-verification.v0.3.json",
        {
            "schema_version": "human-review-rag-source-official-verification-v0.3",
            "status": "HUMAN_DECISION_ACCEPTED__RAG_ADMISSION_ALLOWED",
            "approved_scope": {
                "products": ["DJI Mini 3", "DJI Air 3", "DJI Mavic 3"],
                "language": "zh-CN",
                "region": "China mainland",
            },
        },
    )
    _write_json(
        verification_root / "copyright_policy_gate.v0.3.json",
        {
            "schema_version": "copyright-policy-gate-v0.3",
            "status": "HUMAN_DECISION_RAG_ADMISSION_ALLOWED",
            "scope": {
                "products": ["DJI Mini 3", "DJI Air 3", "DJI Mavic 3"],
                "language": "zh-CN",
                "region": "China mainland",
            },
        },
    )
    _write_json(
        staging_root / "manifest.json",
        {
            "schema_version": "authorized-source-staging-manifest-v0.1",
            "status": "AUTHORIZED_RAW_CANDIDATES__EXTRACTION_NOT_STARTED",
        },
    )


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
