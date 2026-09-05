"""Approved external corpus reader for Slice 10 local pilot retrieval."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from backend.rag.chunk_baseline import (
    ChunkBaselineManifest,
    ChunkBaselineRecord,
    ChunkBaselineStopReason,
    validate_corrected_chunk_baseline_manifest,
)
from backend.rag.controlled_retrieval import (
    ControlledRetrievalRequest,
    ControlledRetrievalResult,
    retrieve_controlled_chunk_metadata,
)
from backend.rag.corpus_readiness import (
    CorpusReadinessReport,
    build_corpus_readiness_report,
)
from backend.rag.manifest import DocumentChunk, DocumentSourceType, SourceLocator


class ExternalCorpusStopReason(StrEnum):
    """Fail-closed reasons for external source-region reads."""

    SOURCE_REGION_ACCEPTED = "SOURCE_REGION_ACCEPTED"
    CORPUS_METADATA_REQUIRED = "CORPUS_METADATA_REQUIRED"
    CHUNK_BASELINE_REQUIRED = "CHUNK_BASELINE_REQUIRED"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    NO_SCOPED_MATCH = "NO_SCOPED_MATCH"
    SCOPED_CANDIDATE_LIMIT = "SCOPED_CANDIDATE_LIMIT"
    RETRIEVAL_TOKEN_BUDGET = "RETRIEVAL_TOKEN_BUDGET"
    TURN_DEADLINE = "TURN_DEADLINE"
    SOURCE_REGION_MISSING = "SOURCE_REGION_MISSING"
    SOURCE_REGION_INVALID = "SOURCE_REGION_INVALID"
    SOURCE_TEXT_CHECKSUM_MISMATCH = "SOURCE_TEXT_CHECKSUM_MISMATCH"
    EXTERNAL_READER_UNAVAILABLE = "EXTERNAL_READER_UNAVAILABLE"


class SourceRegionLoader(Protocol):
    """Injected read-only source-region loader."""

    def load_region(self, record: ChunkBaselineRecord) -> str:
        """Return the external source text for one approved record."""


@dataclass(frozen=True)
class ExternalCorpusReadResult:
    """Ephemeral read result. Source text appears only in in-memory chunks."""

    request: ControlledRetrievalRequest
    chunks: tuple[DocumentChunk, ...]
    metadata_result: ControlledRetrievalResult | None
    corpus_report: CorpusReadinessReport
    manifest: ChunkBaselineManifest | None
    stop_reason: ExternalCorpusStopReason
    reasons: tuple[str, ...] = ()
    persisted_to_repository: bool = False

    @property
    def accepted(self) -> bool:
        return self.stop_reason is ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED

    def safe_metadata(self) -> dict[str, object]:
        """Return a text-free summary suitable for traces or task evidence."""

        return {
            "accepted": self.accepted,
            "stop_reason": self.stop_reason.value,
            "reasons": self.reasons,
            "chunk_count": len(self.chunks),
            "candidate_count": (
                len(self.metadata_result.candidates)
                if self.metadata_result is not None
                else 0
            ),
            "corpus_version": self.manifest.corpus_version if self.manifest else None,
            "persisted_to_repository": self.persisted_to_repository,
            "locators": tuple(chunk.locator.locator for chunk in self.chunks),
            "text_sha256": tuple(
                chunk.metadata["text_sha256"] for chunk in self.chunks
            ),
        }


class ExternalCorpusReadError(RuntimeError):
    """Internal exception for one failed external read boundary."""

    def __init__(self, stop_reason: ExternalCorpusStopReason, message: str) -> None:
        super().__init__(message)
        self.stop_reason = stop_reason
        self.message = message


class ExternalCorpusReader:
    """Validate approved metadata, then load scoped source regions ephemerally."""

    def __init__(
        self,
        *,
        corpus_root: Path | str,
        region_loader: SourceRegionLoader | None = None,
    ) -> None:
        self._corpus_root = Path(corpus_root)
        self._region_loader = region_loader

    def retrieve(
        self,
        *,
        chunk_manifest_path: Path | str,
        request: ControlledRetrievalRequest,
    ) -> ExternalCorpusReadResult:
        corpus_report = build_corpus_readiness_report(self._corpus_root)
        validation = validate_corrected_chunk_baseline_manifest(chunk_manifest_path)
        manifest = validation.manifest
        if manifest is None or not validation.accepted:
            return ExternalCorpusReadResult(
                request=request,
                chunks=(),
                metadata_result=None,
                corpus_report=corpus_report,
                manifest=None,
                stop_reason=_map_chunk_stop_reason(validation.stop_reason),
                reasons=validation.reasons,
            )
        preflight = _validate_corpus_bindings(corpus_report, manifest)
        if preflight is not None:
            stop_reason, reasons = preflight
            return ExternalCorpusReadResult(
                request=request,
                chunks=(),
                metadata_result=None,
                corpus_report=corpus_report,
                manifest=manifest,
                stop_reason=stop_reason,
                reasons=reasons,
            )

        metadata_result = retrieve_controlled_chunk_metadata(manifest, request)
        if metadata_result.stop_reason is not None:
            return ExternalCorpusReadResult(
                request=request,
                chunks=(),
                metadata_result=metadata_result,
                corpus_report=corpus_report,
                manifest=manifest,
                stop_reason=_map_chunk_stop_reason(metadata_result.stop_reason),
                reasons=(metadata_result.stop_reason.value,),
            )

        records_by_id = {record.chunk_id: record for record in manifest.records}
        loader = self._region_loader or PdfPageTextRegionLoader(self._corpus_root)
        chunks: list[DocumentChunk] = []
        try:
            for order, candidate in enumerate(metadata_result.candidates):
                record = records_by_id[candidate.chunk_id]
                text = loader.load_region(record)
                if not text.strip():
                    raise ExternalCorpusReadError(
                        ExternalCorpusStopReason.SOURCE_REGION_INVALID,
                        "source region empty",
                    )
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if digest != record.text_sha256:
                    raise ExternalCorpusReadError(
                        ExternalCorpusStopReason.SOURCE_TEXT_CHECKSUM_MISMATCH,
                        "source region text checksum mismatch",
                    )
                chunks.append(_chunk_from_record(record, text, order))
        except ExternalCorpusReadError as exc:
            return ExternalCorpusReadResult(
                request=request,
                chunks=(),
                metadata_result=metadata_result,
                corpus_report=corpus_report,
                manifest=manifest,
                stop_reason=exc.stop_reason,
                reasons=(exc.message,),
            )

        return ExternalCorpusReadResult(
            request=request,
            chunks=tuple(chunks),
            metadata_result=metadata_result,
            corpus_report=corpus_report,
            manifest=manifest,
            stop_reason=ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED,
        )


class PdfPageTextRegionLoader:
    """Read one approved PDF page through the local pdftotext executable."""

    def __init__(self, corpus_root: Path | str) -> None:
        self._corpus_root = Path(corpus_root).resolve()
        self._source_paths = self._load_source_paths()

    def load_region(self, record: ChunkBaselineRecord) -> str:
        source_path = self._source_paths.get(record.source_ref)
        if source_path is None:
            raise ExternalCorpusReadError(
                ExternalCorpusStopReason.SOURCE_REGION_MISSING,
                "source_ref not found in corpus manifest",
            )
        if not source_path.exists():
            raise ExternalCorpusReadError(
                ExternalCorpusStopReason.SOURCE_REGION_MISSING,
                "source file missing",
            )
        try:
            completed = subprocess.run(
                [
                    "pdftotext",
                    "-f",
                    str(record.page_number),
                    "-l",
                    str(record.page_number),
                    "-layout",
                    str(source_path),
                    "-",
                ],
                check=False,
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError as exc:
            raise ExternalCorpusReadError(
                ExternalCorpusStopReason.EXTERNAL_READER_UNAVAILABLE,
                "pdftotext unavailable",
            ) from exc
        except subprocess.SubprocessError as exc:
            raise ExternalCorpusReadError(
                ExternalCorpusStopReason.EXTERNAL_READER_UNAVAILABLE,
                "source reader failed",
            ) from exc
        if completed.returncode != 0:
            raise ExternalCorpusReadError(
                ExternalCorpusStopReason.SOURCE_REGION_INVALID,
                "source reader returned nonzero",
            )
        try:
            return completed.stdout.decode("utf-8").strip("\f\n\r ")
        except UnicodeDecodeError as exc:
            raise ExternalCorpusReadError(
                ExternalCorpusStopReason.SOURCE_REGION_INVALID,
                "source reader output is not utf-8",
            ) from exc

    def _load_source_paths(self) -> dict[str, Path]:
        manifest_path = self._corpus_root / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExternalCorpusReadError(
                ExternalCorpusStopReason.CORPUS_METADATA_REQUIRED,
                "corpus manifest unavailable",
            ) from exc
        paths: dict[str, Path] = {}
        for relative_path, metadata in _dict(manifest.get("source_files")).items():
            if not isinstance(metadata, dict):
                continue
            source_ref = metadata.get("source_ref")
            if not isinstance(source_ref, str):
                continue
            source_path = (self._corpus_root / relative_path).resolve()
            if not source_path.is_relative_to(self._corpus_root):
                raise ExternalCorpusReadError(
                    ExternalCorpusStopReason.SOURCE_REGION_INVALID,
                    "source path escapes corpus root",
                )
            paths[source_ref] = source_path
        return paths


def _validate_corpus_bindings(
    report: CorpusReadinessReport,
    manifest: ChunkBaselineManifest,
) -> tuple[ExternalCorpusStopReason, tuple[str, ...]] | None:
    if not report.metadata_accepted:
        reasons = tuple(
            item.reason or "corpus metadata rejected" for item in report.rejected_files
        )
        return (
            ExternalCorpusStopReason.CORPUS_METADATA_REQUIRED,
            reasons or (report.stop_reason.value,),
        )
    if report.manifest_sha256 != manifest.corpus_manifest_sha256:
        return (
            ExternalCorpusStopReason.CHECKSUM_MISMATCH,
            ("corpus manifest checksum mismatch",),
        )
    inventory_sha = next(
        (
            item.sha256
            for item in report.accepted_files
            if item.path.endswith("/source_inventory.json")
        ),
        None,
    )
    if inventory_sha != manifest.source_inventory_sha256:
        return (
            ExternalCorpusStopReason.CHECKSUM_MISMATCH,
            ("source inventory checksum mismatch",),
        )
    return None


def _chunk_from_record(
    record: ChunkBaselineRecord,
    text: str,
    order: int,
) -> DocumentChunk:
    return DocumentChunk(
        store_id=record.store_id,
        product_id=record.product_id,
        variant_id=record.variant_id,
        source_id=record.source_id,
        source_type=DocumentSourceType.MANUAL,
        version=record.source_version,
        chunk_id=record.chunk_id,
        order=order,
        locator=SourceLocator(
            source_id=record.source_id,
            version=record.source_version,
            locator=record.locator,
        ),
        heading_path=(record.source_ref, *record.keywords),
        text=text,
        metadata={
            "corpus_version": record.corpus_version,
            "source_ref": record.source_ref,
            "page_number": str(record.page_number),
            "ordinal_start": str(record.ordinal_start),
            "ordinal_end": str(record.ordinal_end),
            "extraction_method": record.extraction_method,
            "text_sha256": record.text_sha256,
            "locator": record.locator,
        },
    )


def _map_chunk_stop_reason(
    reason: ChunkBaselineStopReason,
) -> ExternalCorpusStopReason:
    mapping = {
        ChunkBaselineStopReason.CHUNK_BASELINE_ACCEPTED: (
            ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED
        ),
        ChunkBaselineStopReason.CHUNK_BASELINE_REQUIRED: (
            ExternalCorpusStopReason.CHUNK_BASELINE_REQUIRED
        ),
        ChunkBaselineStopReason.CHUNK_BASELINE_INVALID: (
            ExternalCorpusStopReason.CHUNK_BASELINE_REQUIRED
        ),
        ChunkBaselineStopReason.CHECKSUM_MISMATCH: (
            ExternalCorpusStopReason.CHECKSUM_MISMATCH
        ),
        ChunkBaselineStopReason.SCOPE_MISMATCH: ExternalCorpusStopReason.SCOPE_MISMATCH,
        ChunkBaselineStopReason.NO_SCOPED_MATCH: (
            ExternalCorpusStopReason.NO_SCOPED_MATCH
        ),
        ChunkBaselineStopReason.ACTION_ROUND_LIMIT: (
            ExternalCorpusStopReason.NO_SCOPED_MATCH
        ),
        ChunkBaselineStopReason.SCOPED_CANDIDATE_LIMIT: (
            ExternalCorpusStopReason.SCOPED_CANDIDATE_LIMIT
        ),
        ChunkBaselineStopReason.RETRIEVAL_TOKEN_BUDGET: (
            ExternalCorpusStopReason.RETRIEVAL_TOKEN_BUDGET
        ),
        ChunkBaselineStopReason.TURN_DEADLINE: ExternalCorpusStopReason.TURN_DEADLINE,
    }
    return mapping[reason]


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


__all__ = [
    "ExternalCorpusReadResult",
    "ExternalCorpusReader",
    "ExternalCorpusStopReason",
    "PdfPageTextRegionLoader",
    "SourceRegionLoader",
]
