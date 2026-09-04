"""Read-only readiness checks for externally staged RAG corpus metadata."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

DEFAULT_CORPUS_ROOT = Path(
    "/Users/russeell/Documents/Data-Staging/consumer-drone-agent"
    "/outputs/rag-corpus-20260902-v0.1"
)

EXPECTED_MANIFEST_SCHEMA = "rag-corpus-manifest-v0.1"
EXPECTED_CORPUS_VERSION = "v0.1"
EXPECTED_STATUS = "ADMITTED_SOURCE_CORPUS__LOCATORS_INCLUDED__NOT_INDEXED"
EXPECTED_PRODUCTS = ("DJI Mini 3", "DJI Air 3", "DJI Mavic 3")
EXPECTED_LANGUAGE = "zh-CN"
EXPECTED_REGION = "China mainland"
EXPECTED_ZERO_INDEX_COUNTS = ("chunks", "embeddings", "indexes", "retrieval_runs")


class CorpusReadinessStopReason(StrEnum):
    CORPUS_NOT_INDEXED = "CORPUS_NOT_INDEXED"
    CORPUS_MANIFEST_MISSING = "CORPUS_MANIFEST_MISSING"
    CORPUS_CHECKSUM_MISMATCH = "CORPUS_CHECKSUM_MISMATCH"
    CORPUS_METADATA_MISMATCH = "CORPUS_METADATA_MISMATCH"


class CorpusFileValidation(BaseModel):
    """Metadata-only validation result for one staged file path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: NonEmptyString
    sha256: NonEmptyString | None = None
    record_count: int | None = Field(default=None, ge=0)
    accepted: bool
    reason: NonEmptyString | None = None


class CorpusReadinessReport(BaseModel):
    """Internal readiness report for a staged corpus manifest.

    This object is intentionally not a public wire contract and never carries source
    document text, locator verbatim text, embeddings, indexes, or retrieval results.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_path: NonEmptyString
    manifest_sha256: NonEmptyString | None = None
    corpus_version: NonEmptyString | None = None
    source_count: int = Field(ge=0)
    page_locator_count: int = Field(ge=0)
    counts: dict[NonEmptyString, int | bool] = Field(default_factory=dict)
    decision_bindings: dict[NonEmptyString, NonEmptyString] = Field(
        default_factory=dict
    )
    accepted_files: tuple[CorpusFileValidation, ...] = ()
    rejected_files: tuple[CorpusFileValidation, ...] = ()
    stop_reason: CorpusReadinessStopReason

    @property
    def metadata_accepted(self) -> bool:
        return not self.rejected_files and self.stop_reason is (
            CorpusReadinessStopReason.CORPUS_NOT_INDEXED
        )

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def build_corpus_readiness_report(
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
) -> CorpusReadinessReport:
    """Validate one approved external corpus metadata root without writing to it."""

    root = Path(corpus_root)
    manifest_path = root / "manifest.json"
    manifest_path_text = str(manifest_path)
    if not manifest_path.exists():
        return CorpusReadinessReport(
            manifest_path=manifest_path_text,
            source_count=0,
            page_locator_count=0,
            stop_reason=CorpusReadinessStopReason.CORPUS_MANIFEST_MISSING,
            rejected_files=(
                CorpusFileValidation(
                    path=manifest_path_text,
                    accepted=False,
                    reason="manifest missing",
                ),
            ),
        )

    accepted: list[CorpusFileValidation] = []
    rejected: list[CorpusFileValidation] = []
    manifest_sha256 = _sha256_file(manifest_path)
    manifest = _read_json(manifest_path)
    accepted.append(
        CorpusFileValidation(
            path=manifest_path_text,
            sha256=manifest_sha256,
            accepted=True,
        )
    )

    _validate_manifest_shape(manifest, manifest_path_text, rejected)
    decision_bindings = _string_dict(manifest.get("decision_bindings"))
    counts = _counts_dict(manifest.get("counts"))

    inventory_by_path = _load_source_inventory(root, manifest, accepted, rejected)
    source_count = len(_dict(manifest.get("source_files")))
    page_locator_count = _validate_derived_files(
        root,
        manifest,
        inventory_by_path,
        accepted,
        rejected,
    )
    _validate_decision_bindings(root, manifest, accepted, rejected)

    stop_reason = _select_stop_reason(rejected, counts)
    return CorpusReadinessReport(
        manifest_path=manifest_path_text,
        manifest_sha256=manifest_sha256,
        corpus_version=_str_or_none(manifest.get("corpus_version")),
        source_count=source_count,
        page_locator_count=page_locator_count,
        counts=counts,
        decision_bindings=decision_bindings,
        accepted_files=tuple(
            sorted(accepted, key=lambda item: (item.path, item.reason or ""))
        ),
        rejected_files=tuple(
            sorted(rejected, key=lambda item: (item.path, item.reason or ""))
        ),
        stop_reason=stop_reason,
    )


def _validate_manifest_shape(
    manifest: dict[str, Any],
    manifest_path: str,
    rejected: list[CorpusFileValidation],
) -> None:
    if manifest.get("schema_version") != EXPECTED_MANIFEST_SCHEMA:
        _reject(rejected, manifest_path, "manifest schema mismatch")
    if manifest.get("corpus_version") != EXPECTED_CORPUS_VERSION:
        _reject(rejected, manifest_path, "corpus version mismatch")
    if manifest.get("status") != EXPECTED_STATUS:
        _reject(rejected, manifest_path, "manifest status not admitted")
    if manifest.get("immutable") is not True:
        _reject(rejected, manifest_path, "manifest must be immutable")

    scope = _dict(manifest.get("scope"))
    if tuple(scope.get("products", ())) != EXPECTED_PRODUCTS:
        _reject(rejected, manifest_path, "manifest product scope mismatch")
    if scope.get("language") != EXPECTED_LANGUAGE:
        _reject(rejected, manifest_path, "manifest language mismatch")
    if scope.get("region") != EXPECTED_REGION:
        _reject(rejected, manifest_path, "manifest region mismatch")
    if not _string_dict(manifest.get("decision_bindings")):
        _reject(rejected, manifest_path, "decision bindings missing")


def _load_source_inventory(
    root: Path,
    manifest: dict[str, Any],
    accepted: list[CorpusFileValidation],
    rejected: list[CorpusFileValidation],
) -> dict[str, dict[str, Any]]:
    inventory_path = root / "source_inventory.json"
    if not inventory_path.exists():
        _reject(rejected, str(inventory_path), "source inventory missing")
        return {}

    inventory = _read_json(inventory_path)
    accepted.append(
        CorpusFileValidation(
            path=str(inventory_path),
            sha256=_sha256_file(inventory_path),
            accepted=True,
        )
    )
    if inventory.get("schema_version") != "rag-corpus-source-inventory-v0.1":
        _reject(rejected, str(inventory_path), "source inventory schema mismatch")
    if inventory.get("corpus_version") != manifest.get("corpus_version"):
        _reject(rejected, str(inventory_path), "source inventory version mismatch")

    records = inventory.get("records")
    if not isinstance(records, list):
        _reject(rejected, str(inventory_path), "source inventory records missing")
        return {}

    by_path: dict[str, dict[str, Any]] = {}
    source_files = _dict(manifest.get("source_files"))
    for record in records:
        if not isinstance(record, dict):
            _reject(rejected, str(inventory_path), "source inventory record invalid")
            continue
        source_path = _str_or_none(record.get("path"))
        if source_path is None:
            _reject(rejected, str(inventory_path), "source inventory path missing")
            continue
        by_path[source_path] = record
        source_meta = _dict(source_files.get(source_path))
        if not source_meta:
            _reject(rejected, source_path, "source inventory path not in manifest")
            continue
        if record.get("source_id") != source_meta.get("source_ref"):
            _reject(rejected, source_path, "source_ref mismatch")
        if record.get("sha256") != source_meta.get("sha256"):
            _reject(rejected, source_path, "source sha256 mismatch")
        if record.get("pages") != source_meta.get("pages"):
            _reject(rejected, source_path, "source page count mismatch")
        if record.get("language") != EXPECTED_LANGUAGE:
            _reject(rejected, source_path, "source language mismatch")
        if record.get("region") != EXPECTED_REGION:
            _reject(rejected, source_path, "source region mismatch")
    if len(by_path) != len(source_files):
        _reject(rejected, str(inventory_path), "source count mismatch")
    return by_path


def _validate_derived_files(
    root: Path,
    manifest: dict[str, Any],
    inventory_by_path: dict[str, dict[str, Any]],
    accepted: list[CorpusFileValidation],
    rejected: list[CorpusFileValidation],
) -> int:
    derived_files = _dict(manifest.get("derived_files"))
    source_files = _dict(manifest.get("source_files"))
    total_records = 0
    for source_path, source_meta in source_files.items():
        inventory_record = inventory_by_path.get(source_path)
        if inventory_record is None:
            continue
        locator_path_value = _str_or_none(inventory_record.get("locator_path"))
        if locator_path_value is None:
            _reject(rejected, source_path, "locator path missing")
            continue
        locator_meta = _dict(derived_files.get(locator_path_value))
        locator_path = root / locator_path_value
        if not locator_path.exists():
            _reject(rejected, str(locator_path), "locator file missing")
            continue
        actual_sha = _sha256_file(locator_path)
        expected_sha = _str_or_none(locator_meta.get("sha256"))
        if actual_sha != expected_sha:
            _reject(
                rejected,
                str(locator_path),
                "locator sha256 mismatch",
                sha256=actual_sha,
            )
            continue
        records = _validate_locator_records(
            locator_path,
            source_meta,
            inventory_record,
            rejected,
        )
        expected_records = locator_meta.get("records")
        if records != expected_records:
            _reject(
                rejected,
                str(locator_path),
                "locator record count mismatch",
                sha256=actual_sha,
                record_count=records,
            )
            continue
        total_records += records
        accepted.append(
            CorpusFileValidation(
                path=str(locator_path),
                sha256=actual_sha,
                record_count=records,
                accepted=True,
            )
        )

    overlay_meta = _dict(derived_files.get("derived/mavic_3_scope_overlay.v0.1.json"))
    if overlay_meta:
        overlay_path = root / "derived/mavic_3_scope_overlay.v0.1.json"
        _validate_overlay(overlay_path, overlay_meta, accepted, rejected)

    expected_total = _counts_dict(manifest.get("counts")).get("page_locator_records")
    if expected_total is not None and total_records != expected_total:
        _reject(
            rejected,
            str(root / "manifest.json"),
            "total page locator count mismatch",
            record_count=total_records,
        )
    return total_records


def _validate_locator_records(
    locator_path: Path,
    source_meta: dict[str, Any],
    inventory_record: dict[str, Any],
    rejected: list[CorpusFileValidation],
) -> int:
    records = 0
    expected_sha = source_meta.get("sha256")
    expected_language = inventory_record.get("language")
    expected_region = inventory_record.get("region")
    expected_scope = inventory_record.get("product_scope")
    with locator_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                _reject(rejected, str(locator_path), "locator json invalid")
                continue
            records += 1
            if record.get("record_type") != "ordered_page_locator":
                _reject(rejected, str(locator_path), "locator record_type mismatch")
            if record.get("source_sha256") != expected_sha:
                _reject(rejected, str(locator_path), "locator source sha256 mismatch")
            if record.get("language") != expected_language:
                _reject(rejected, str(locator_path), "locator language mismatch")
            if record.get("region") != expected_region:
                _reject(rejected, str(locator_path), "locator region mismatch")
            if not _locator_scope_matches_inventory(
                _str_or_none(record.get("product_scope")),
                _str_or_none(expected_scope),
            ):
                _reject(rejected, str(locator_path), "locator product scope mismatch")
            if record.get("ordinal") != line_number:
                _reject(rejected, str(locator_path), "locator ordinal mismatch")
    return records


def _validate_overlay(
    overlay_path: Path,
    overlay_meta: dict[str, Any],
    accepted: list[CorpusFileValidation],
    rejected: list[CorpusFileValidation],
) -> None:
    if not overlay_path.exists():
        _reject(rejected, str(overlay_path), "scope overlay missing")
        return
    actual_sha = _sha256_file(overlay_path)
    if actual_sha != overlay_meta.get("sha256"):
        _reject(rejected, str(overlay_path), "scope overlay sha256 mismatch")
        return
    overlay = _read_json(overlay_path)
    if overlay.get("schema_version") != "source-scope-overlay-v0.1":
        _reject(rejected, str(overlay_path), "scope overlay schema mismatch")
        return
    accepted.append(
        CorpusFileValidation(path=str(overlay_path), sha256=actual_sha, accepted=True)
    )


def _validate_decision_bindings(
    root: Path,
    manifest: dict[str, Any],
    accepted: list[CorpusFileValidation],
    rejected: list[CorpusFileValidation],
) -> None:
    bindings = _string_dict(manifest.get("decision_bindings"))
    expected = {
        "human_review": (
            "human-review-rag-source-official-verification-v0.3",
            "HUMAN_DECISION_ACCEPTED__RAG_ADMISSION_ALLOWED",
            "approved_scope",
        ),
        "copyright_policy": (
            "copyright-policy-gate-v0.3",
            "HUMAN_DECISION_RAG_ADMISSION_ALLOWED",
            "scope",
        ),
        "source_staging": (
            "authorized-source-staging-manifest-v0.1",
            "AUTHORIZED_RAW_CANDIDATES__EXTRACTION_NOT_STARTED",
            None,
        ),
    }
    for binding_name, (schema, status, scope_key) in expected.items():
        binding = bindings.get(binding_name)
        if binding is None:
            _reject(rejected, str(root / "manifest.json"), f"{binding_name} missing")
            continue
        binding_path = (root / binding).resolve()
        if not binding_path.exists():
            _reject(rejected, str(binding_path), f"{binding_name} file missing")
            continue
        document = _read_json(binding_path)
        accepted.append(
            CorpusFileValidation(
                path=str(binding_path),
                sha256=_sha256_file(binding_path),
                accepted=True,
            )
        )
        if document.get("schema_version") != schema:
            _reject(rejected, str(binding_path), f"{binding_name} schema mismatch")
        if document.get("status") != status:
            _reject(rejected, str(binding_path), f"{binding_name} status mismatch")
        if scope_key is not None:
            _validate_decision_scope(
                binding_path, _dict(document.get(scope_key)), rejected
            )


def _validate_decision_scope(
    binding_path: Path,
    scope: dict[str, Any],
    rejected: list[CorpusFileValidation],
) -> None:
    if tuple(scope.get("products", ())) != EXPECTED_PRODUCTS:
        _reject(rejected, str(binding_path), "decision product scope mismatch")
    if scope.get("language") != EXPECTED_LANGUAGE:
        _reject(rejected, str(binding_path), "decision language mismatch")
    if scope.get("region") != EXPECTED_REGION:
        _reject(rejected, str(binding_path), "decision region mismatch")


def _select_stop_reason(
    rejected: list[CorpusFileValidation],
    counts: dict[str, int | bool],
) -> CorpusReadinessStopReason:
    if any("sha256 mismatch" in (item.reason or "") for item in rejected):
        return CorpusReadinessStopReason.CORPUS_CHECKSUM_MISMATCH
    if rejected:
        return CorpusReadinessStopReason.CORPUS_METADATA_MISMATCH
    if any(counts.get(key) != 0 for key in EXPECTED_ZERO_INDEX_COUNTS):
        return CorpusReadinessStopReason.CORPUS_METADATA_MISMATCH
    return CorpusReadinessStopReason.CORPUS_NOT_INDEXED


def _locator_scope_matches_inventory(
    locator_scope: str | None,
    inventory_scope: str | None,
) -> bool:
    if locator_scope is None or inventory_scope is None:
        return False
    if locator_scope == inventory_scope:
        return True
    return inventory_scope.startswith(f"{locator_scope};")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject(
    rejected: list[CorpusFileValidation],
    path: str,
    reason: str,
    *,
    sha256: str | None = None,
    record_count: int | None = None,
) -> None:
    rejected.append(
        CorpusFileValidation(
            path=path,
            sha256=sha256,
            record_count=record_count,
            accepted=False,
            reason=reason,
        )
    )


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if isinstance(item, str)}


def _counts_dict(value: object) -> dict[str, int | bool]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int | bool] = {}
    for key, item in value.items():
        if isinstance(item, bool | int):
            counts[str(key)] = item
    return counts


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = [
    "CorpusFileValidation",
    "CorpusReadinessReport",
    "CorpusReadinessStopReason",
    "DEFAULT_CORPUS_ROOT",
    "build_corpus_readiness_report",
]
