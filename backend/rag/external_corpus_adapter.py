"""Translate one ephemeral external corpus read into the existing RAG result."""

from __future__ import annotations

import hashlib
from typing import Annotated

from pydantic import Field, StringConstraints

from backend.common import ObjectScope
from backend.rag.chunk_baseline import ChunkBaselineRecord
from backend.rag.controlled_retrieval import (
    MAX_ACTION_ROUNDS,
    TURN_DEADLINE_MS,
    ControlledRetrievalCandidate,
    ControlledRetrievalRequest,
)
from backend.rag.external_corpus_reader import (
    ExternalCorpusReader,
    ExternalCorpusReadResult,
    ExternalCorpusStopReason,
)
from backend.rag.manifest import DocumentChunk, DocumentSourceType, RagModel
from backend.rag.manifest_identity import CorpusManifestIdentity
from backend.rag.retrieval import RetrievalRequest, RetrievalResult, RetrievalStrategy
from backend.rag.scope_binding import CorpusScopeBinding

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
type Sha256String = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ExternalCorpusAdapterError(RuntimeError):
    """A request cannot safely cross the external corpus adapter boundary."""

    def __init__(self, stop_reason: ExternalCorpusStopReason, message: str) -> None:
        super().__init__(message)
        self.stop_reason = stop_reason
        self.message = message


class CorpusSourceVersion(RagModel):
    """Source revision retained independently from manifest identity."""

    source_id: NonEmptyString
    version: NonEmptyString


class ExternalCorpusRetrievalResult(RagModel):
    """Adapter output that stops failed reads before the Evidence Gate."""

    request: RetrievalRequest
    controlled_request: ControlledRetrievalRequest
    retrieval: RetrievalResult | None = None
    manifest_identity: CorpusManifestIdentity | None = None
    source_versions: tuple[CorpusSourceVersion, ...] = ()
    action_rounds_used: int = Field(ge=0, le=2)
    retrieval_tokens_used: int = Field(ge=0)
    filtered_out_count: int = Field(ge=0)
    stop_reason: ExternalCorpusStopReason
    reasons: tuple[NonEmptyString, ...] = ()
    persisted_to_repository: bool = False

    @property
    def accepted(self) -> bool:
        return (
            self.retrieval is not None
            and self.stop_reason is ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED
        )


def build_controlled_retrieval_request(
    request: RetrievalRequest,
    *,
    binding: CorpusScopeBinding,
    manifest_sha256: str,
    max_action_rounds: int = MAX_ACTION_ROUNDS,
    turn_deadline_ms: int = TURN_DEADLINE_MS,
) -> ControlledRetrievalRequest:
    """Translate a canonical request only after exact binding/checksum checks."""

    if request.turn_target != binding.canonical_scope:
        raise ExternalCorpusAdapterError(
            ExternalCorpusStopReason.SCOPE_MISMATCH,
            "retrieval target does not match corpus binding",
        )
    if binding.manifest_sha256 != manifest_sha256:
        raise ExternalCorpusAdapterError(
            ExternalCorpusStopReason.CHECKSUM_MISMATCH,
            "retrieval manifest checksum does not match corpus binding",
        )
    return ControlledRetrievalRequest(
        store_id=binding.canonical_scope.store_id,
        product_id=binding.canonical_scope.product_id,
        variant_id=binding.canonical_scope.variant_id,
        query=request.question,
        field_hint=request.field_hint,
        max_candidates=request.k,
        max_action_rounds=max_action_rounds,
        max_retrieval_tokens=request.max_retrieval_tokens,
        turn_deadline_ms=turn_deadline_ms,
    )


def adapt_external_corpus_result(
    result: ExternalCorpusReadResult,
    *,
    expected_controlled_request: ControlledRetrievalRequest,
    expected_manifest_sha256: Sha256String,
) -> ExternalCorpusRetrievalResult:
    """Adapt one already-completed read; this function never invokes retrieval."""

    request = _retrieval_request(result.request)
    identity = result.manifest_identity
    metadata_result = result.metadata_result
    filtered_out_count = (
        metadata_result.filtered_out_count if metadata_result is not None else 0
    )
    action_rounds_used = (
        metadata_result.action_rounds_used if metadata_result is not None else 0
    )
    retrieval_tokens_used = (
        metadata_result.retrieval_tokens_used if metadata_result is not None else 0
    )
    source_versions = _source_versions(result.chunks)
    stop_reason = result.stop_reason
    reasons = result.reasons

    if result.request != expected_controlled_request:
        stop_reason = ExternalCorpusStopReason.SCOPE_MISMATCH
        reasons = ("reader returned a request different from the caller request",)
    elif metadata_result is not None and metadata_result.request != result.request:
        stop_reason = ExternalCorpusStopReason.SCOPE_MISMATCH
        reasons = ("metadata result request differs from the reader request",)
    elif (
        metadata_result is not None
        and action_rounds_used > result.request.max_action_rounds
    ):
        stop_reason = ExternalCorpusStopReason.ACTION_ROUND_LIMIT
        reasons = ("reader exceeded the configured action-round budget",)
    elif (
        metadata_result is not None
        and retrieval_tokens_used > result.request.max_retrieval_tokens
        and stop_reason is ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED
    ):
        stop_reason = ExternalCorpusStopReason.RETRIEVAL_TOKEN_BUDGET
        reasons = ("reader exceeded the configured retrieval-token budget",)

    if stop_reason is ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED:
        if identity is None:
            stop_reason = ExternalCorpusStopReason.CORPUS_METADATA_REQUIRED
            reasons = ("accepted read is missing manifest identity",)
        elif identity.manifest_sha256 != expected_manifest_sha256:
            stop_reason = ExternalCorpusStopReason.CHECKSUM_MISMATCH
            reasons = ("returned manifest identity does not match the bound checksum",)
        elif not result.chunks:
            stop_reason = ExternalCorpusStopReason.EMPTY_RESULT
            reasons = ("accepted read returned no source regions",)
        elif not _manifest_checksum_matches_report(result):
            stop_reason = ExternalCorpusStopReason.CHECKSUM_MISMATCH
            reasons = ("manifest identity does not match the corpus readiness report",)
        elif not _versions_match_manifest(result):
            stop_reason = ExternalCorpusStopReason.VERSION_MISMATCH
            reasons = ("chunk source version is not bound to the admitted manifest",)
        else:
            retrieval = RetrievalResult(
                request=request,
                evidence=result.chunks,
                retrieval_strategy=RetrievalStrategy.KEYWORD_OVERLAP,
                index_version=identity.index_version,
                filtered_out_count=filtered_out_count,
            )
            return ExternalCorpusRetrievalResult(
                request=request,
                controlled_request=result.request,
                retrieval=retrieval,
                manifest_identity=identity,
                source_versions=source_versions,
                action_rounds_used=action_rounds_used,
                retrieval_tokens_used=retrieval_tokens_used,
                filtered_out_count=filtered_out_count,
                stop_reason=stop_reason,
                reasons=reasons,
                persisted_to_repository=result.persisted_to_repository,
            )

    return ExternalCorpusRetrievalResult(
        request=request,
        controlled_request=result.request,
        manifest_identity=identity,
        source_versions=source_versions,
        action_rounds_used=action_rounds_used,
        retrieval_tokens_used=retrieval_tokens_used,
        filtered_out_count=filtered_out_count,
        stop_reason=stop_reason,
        reasons=reasons,
        persisted_to_repository=result.persisted_to_repository,
    )


def retrieve_external_corpus(
    reader: ExternalCorpusReader,
    *,
    chunk_manifest_path: str,
    request: RetrievalRequest,
    binding: CorpusScopeBinding,
    manifest_sha256: str,
    max_action_rounds: int = MAX_ACTION_ROUNDS,
    turn_deadline_ms: int = TURN_DEADLINE_MS,
) -> ExternalCorpusRetrievalResult:
    """Execute the bounded flow exactly once and adapt its ephemeral result."""

    controlled_request = build_controlled_retrieval_request(
        request,
        binding=binding,
        manifest_sha256=manifest_sha256,
        max_action_rounds=max_action_rounds,
        turn_deadline_ms=turn_deadline_ms,
    )
    external_result = reader.retrieve(
        chunk_manifest_path=chunk_manifest_path,
        request=controlled_request,
    )
    return adapt_external_corpus_result(
        external_result,
        expected_controlled_request=controlled_request,
        expected_manifest_sha256=manifest_sha256,
    )


def _retrieval_request(request: ControlledRetrievalRequest) -> RetrievalRequest:
    return RetrievalRequest(
        turn_target=ObjectScope(
            store_id=request.store_id,
            product_id=request.product_id,
            variant_id=request.variant_id,
        ),
        question=request.query,
        k=request.max_candidates,
        field_hint=request.field_hint,
        max_retrieval_tokens=request.max_retrieval_tokens,
    )


def _source_versions(
    chunks: tuple[DocumentChunk, ...],
) -> tuple[CorpusSourceVersion, ...]:
    return tuple(
        CorpusSourceVersion(source_id=source_id, version=version)
        for source_id, version in sorted(
            {(chunk.source_id, chunk.version) for chunk in chunks}
        )
    )


def _versions_match_manifest(result: ExternalCorpusReadResult) -> bool:
    if (
        result.manifest is None
        or result.manifest_identity is None
        or result.metadata_result is None
    ):
        return False
    records_by_id = {record.chunk_id: record for record in result.manifest.records}
    candidates_by_id = {
        candidate.chunk_id: candidate for candidate in result.metadata_result.candidates
    }
    candidate_ids = tuple(
        candidate.chunk_id for candidate in result.metadata_result.candidates
    )
    chunk_ids = tuple(chunk.chunk_id for chunk in result.chunks)
    if len(candidate_ids) != len(set(candidate_ids)) or len(chunk_ids) != len(
        set(chunk_ids)
    ):
        return False
    if chunk_ids != candidate_ids:
        return False
    for chunk in result.chunks:
        record = records_by_id.get(chunk.chunk_id)
        candidate = candidates_by_id.get(chunk.chunk_id)
        if record is None or candidate is None:
            return False
        if not _candidate_matches_record(candidate, record):
            return False
        if not _scope_matches(record, result.request):
            return False
        if (
            chunk.store_id != record.store_id
            or chunk.product_id != record.product_id
            or chunk.variant_id != record.variant_id
            or chunk.source_id != record.source_id
            or chunk.source_type is not DocumentSourceType.MANUAL
            or chunk.version != record.source_version
            or chunk.locator.source_id != record.source_id
            or chunk.locator.version != record.source_version
            or chunk.locator.locator != record.locator
            or chunk.metadata.get("corpus_version") != record.corpus_version
            or chunk.metadata.get("source_ref") != record.source_ref
            or chunk.metadata.get("page_number") != str(record.page_number)
            or chunk.metadata.get("ordinal_start") != str(record.ordinal_start)
            or chunk.metadata.get("ordinal_end") != str(record.ordinal_end)
            or chunk.metadata.get("text_sha256") != record.text_sha256
            or chunk.metadata.get("locator") != record.locator
            or chunk.metadata.get("language") != record.language
            or chunk.metadata.get("region") != record.region
        ):
            return False
        if (
            chunk.metadata.get("manifest_identity")
            != result.manifest_identity.index_version
        ):
            return False
        if hashlib.sha256(chunk.text.encode("utf-8")).hexdigest() != record.text_sha256:
            return False
    return True


def _candidate_matches_record(
    candidate: ControlledRetrievalCandidate,
    record: ChunkBaselineRecord,
) -> bool:
    return (
        candidate.chunk_id == record.chunk_id
        and candidate.source_id == record.source_id
        and candidate.source_ref == record.source_ref
        and candidate.locator == record.locator
        and candidate.product_id == record.product_id
        and candidate.variant_id == record.variant_id
        and candidate.page_number == record.page_number
        and candidate.ordinal_start == record.ordinal_start
        and candidate.ordinal_end == record.ordinal_end
        and candidate.text_sha256 == record.text_sha256
        and candidate.token_estimate == record.token_estimate
    )


def _scope_matches(
    record: ChunkBaselineRecord,
    request: ControlledRetrievalRequest,
) -> bool:
    if record.store_id != request.store_id or record.product_id != request.product_id:
        return False
    if request.variant_id is None:
        return record.variant_id is None
    return record.variant_id in (None, request.variant_id)


def _manifest_checksum_matches_report(result: ExternalCorpusReadResult) -> bool:
    return (
        result.manifest_identity is not None
        and result.corpus_report.manifest_sha256
        == result.manifest_identity.manifest_sha256
    )


__all__ = [
    "CorpusSourceVersion",
    "ExternalCorpusAdapterError",
    "ExternalCorpusRetrievalResult",
    "adapt_external_corpus_result",
    "build_controlled_retrieval_request",
    "retrieve_external_corpus",
]
