"""S09 corrected chunk-baseline validation and metadata-only experiment helpers."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
type Sha256String = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

EXPECTED_CHUNK_BASELINE_SCHEMA = "rag-corrected-chunk-baseline-v0.1"
EXPECTED_CHUNK_BASELINE_STATUS = "APPROVED_FOR_CONTROLLED_RETRIEVAL_EXPERIMENT"
EXPECTED_CORPUS_VERSION = "v0.1"
EXPECTED_LANGUAGE = "zh-CN"
EXPECTED_REGION = "China mainland"


class ChunkBaselineStopReason(StrEnum):
    CHUNK_BASELINE_ACCEPTED = "CHUNK_BASELINE_ACCEPTED"
    CHUNK_BASELINE_REQUIRED = "CHUNK_BASELINE_REQUIRED"
    CHUNK_BASELINE_INVALID = "CHUNK_BASELINE_INVALID"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    NO_SCOPED_MATCH = "NO_SCOPED_MATCH"
    ACTION_ROUND_LIMIT = "ACTION_ROUND_LIMIT"
    SCOPED_CANDIDATE_LIMIT = "SCOPED_CANDIDATE_LIMIT"
    RETRIEVAL_TOKEN_BUDGET = "RETRIEVAL_TOKEN_BUDGET"
    TURN_DEADLINE = "TURN_DEADLINE"


class ChunkBaselineRecord(BaseModel):
    """One metadata-only chunk locator. It must not carry source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: NonEmptyString
    source_id: NonEmptyString
    source_ref: NonEmptyString
    source_version: NonEmptyString
    corpus_version: NonEmptyString
    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    language: NonEmptyString
    region: NonEmptyString
    page_number: int = Field(ge=1)
    ordinal_start: int = Field(ge=0)
    ordinal_end: int = Field(ge=0)
    extraction_method: NonEmptyString
    text_sha256: Sha256String
    locator: NonEmptyString
    token_estimate: int = Field(ge=0)
    keywords: tuple[NonEmptyString, ...] = ()
    overlay_decision: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_record(self) -> ChunkBaselineRecord:
        if self.ordinal_end < self.ordinal_start:
            raise ValueError(
                "ordinal_end must be greater than or equal to ordinal_start"
            )
        expected_prefix = f"rag://{self.source_id}@{self.source_version}/"
        if not self.locator.startswith(expected_prefix):
            raise ValueError("locator must be bound to source_id and source_version")
        if self.language != EXPECTED_LANGUAGE:
            raise ValueError("record language mismatch")
        if self.region != EXPECTED_REGION:
            raise ValueError("record region mismatch")
        if self.corpus_version != EXPECTED_CORPUS_VERSION:
            raise ValueError("record corpus_version mismatch")
        return self


class ChunkBaselineManifest(BaseModel):
    """Append-only corrected chunk manifest for a controlled offline experiment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: NonEmptyString
    status: NonEmptyString
    corpus_version: NonEmptyString
    append_only: bool
    corpus_manifest_sha256: Sha256String
    source_inventory_sha256: Sha256String
    records: tuple[ChunkBaselineRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> ChunkBaselineManifest:
        if self.schema_version != EXPECTED_CHUNK_BASELINE_SCHEMA:
            raise ValueError("chunk baseline schema mismatch")
        if self.status != EXPECTED_CHUNK_BASELINE_STATUS:
            raise ValueError("chunk baseline status not approved")
        if self.corpus_version != EXPECTED_CORPUS_VERSION:
            raise ValueError("chunk baseline corpus_version mismatch")
        if not self.append_only:
            raise ValueError("chunk baseline must be append_only")
        chunk_ids = [record.chunk_id for record in self.records]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk_id values must be unique")
        return self


class ChunkBaselineValidationReport(BaseModel):
    """Internal validation report; no raw text or chunk body is represented."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_path: NonEmptyString
    manifest_sha256: Sha256String | None = None
    accepted: bool
    corpus_version: NonEmptyString | None = None
    chunk_count: int = Field(ge=0)
    stop_reason: ChunkBaselineStopReason
    reasons: tuple[NonEmptyString, ...] = ()
    manifest: ChunkBaselineManifest | None = None


class ChunkMetadataExperimentReport(BaseModel):
    """Deterministic metadata-only replay output for S09-T02."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    corpus_version: NonEmptyString
    chunk_count: int = Field(ge=0)
    metadata_digest: Sha256String
    rejected_count: int = Field(ge=0)
    stop_reason: ChunkBaselineStopReason
    persisted_to_repository: bool = False


def validate_corrected_chunk_baseline_manifest(
    manifest_path: Path | str,
) -> ChunkBaselineValidationReport:
    """Validate an external corrected chunk manifest without writing anywhere."""

    path = Path(manifest_path)
    path_text = str(path)
    if not path.exists():
        return ChunkBaselineValidationReport(
            manifest_path=path_text,
            accepted=False,
            chunk_count=0,
            stop_reason=ChunkBaselineStopReason.CHUNK_BASELINE_REQUIRED,
            reasons=("manifest missing",),
        )
    manifest_sha256 = _sha256_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = ChunkBaselineManifest.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        reason = _classify_validation_error(str(exc))
        return ChunkBaselineValidationReport(
            manifest_path=path_text,
            manifest_sha256=manifest_sha256,
            accepted=False,
            chunk_count=0,
            stop_reason=reason,
            reasons=(str(exc),),
        )
    return ChunkBaselineValidationReport(
        manifest_path=path_text,
        manifest_sha256=manifest_sha256,
        accepted=True,
        corpus_version=manifest.corpus_version,
        chunk_count=len(manifest.records),
        stop_reason=ChunkBaselineStopReason.CHUNK_BASELINE_ACCEPTED,
        manifest=manifest,
    )


def run_ephemeral_chunk_metadata_experiment(
    manifest: ChunkBaselineManifest,
) -> ChunkMetadataExperimentReport:
    """Build a deterministic metadata digest without persisting generated chunks."""

    ordered = sorted(
        manifest.records,
        key=lambda record: (
            record.source_id,
            record.page_number,
            record.ordinal_start,
            record.chunk_id,
        ),
    )
    metadata = [
        record.model_dump(
            mode="json",
            include={
                "chunk_id",
                "source_id",
                "source_ref",
                "source_version",
                "corpus_version",
                "store_id",
                "product_id",
                "variant_id",
                "language",
                "region",
                "page_number",
                "ordinal_start",
                "ordinal_end",
                "extraction_method",
                "text_sha256",
                "locator",
                "token_estimate",
                "keywords",
                "overlay_decision",
            },
        )
        for record in ordered
    ]
    digest = hashlib.sha256(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ChunkMetadataExperimentReport(
        accepted=True,
        corpus_version=manifest.corpus_version,
        chunk_count=len(ordered),
        metadata_digest=digest,
        rejected_count=0,
        stop_reason=ChunkBaselineStopReason.CHUNK_BASELINE_ACCEPTED,
    )


def _classify_validation_error(message: str) -> ChunkBaselineStopReason:
    if "sha256" in message:
        return ChunkBaselineStopReason.CHECKSUM_MISMATCH
    if any(term in message for term in ("language", "region", "scope")):
        return ChunkBaselineStopReason.SCOPE_MISMATCH
    return ChunkBaselineStopReason.CHUNK_BASELINE_INVALID


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ChunkBaselineManifest",
    "ChunkBaselineRecord",
    "ChunkBaselineStopReason",
    "ChunkBaselineValidationReport",
    "ChunkMetadataExperimentReport",
    "EXPECTED_CHUNK_BASELINE_SCHEMA",
    "EXPECTED_CHUNK_BASELINE_STATUS",
    "run_ephemeral_chunk_metadata_experiment",
    "validate_corrected_chunk_baseline_manifest",
]
