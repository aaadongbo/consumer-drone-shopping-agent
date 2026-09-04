"""S09 controlled lexical retrieval over corrected chunk metadata."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.rag.chunk_baseline import (
    ChunkBaselineManifest,
    ChunkBaselineRecord,
    ChunkBaselineStopReason,
)

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
type Sha256String = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

MAX_ACTION_ROUNDS = 2
MAX_SCOPED_CANDIDATES = 10
MAX_RETRIEVAL_TOKENS = 4000
TURN_DEADLINE_MS = 8000


class ControlledRetrievalRequest(BaseModel):
    """Internal S09 retrieval request for one resolved Turn Target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    query: NonEmptyString
    field_hint: NonEmptyString | None = None
    max_candidates: int = Field(default=MAX_SCOPED_CANDIDATES, ge=1, le=10)
    max_action_rounds: int = Field(default=MAX_ACTION_ROUNDS, ge=1, le=2)
    max_retrieval_tokens: int = Field(default=MAX_RETRIEVAL_TOKENS, ge=1, le=4000)
    turn_deadline_ms: int = Field(default=TURN_DEADLINE_MS, ge=1, le=8000)


class ControlledRetrievalCandidate(BaseModel):
    """Returned locator metadata. It intentionally excludes source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: NonEmptyString
    source_id: NonEmptyString
    source_ref: NonEmptyString
    locator: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    page_number: int = Field(ge=1)
    ordinal_start: int = Field(ge=0)
    ordinal_end: int = Field(ge=0)
    score: int = Field(ge=0)
    text_sha256: Sha256String
    token_estimate: int = Field(ge=0)


class ControlledRetrievalResult(BaseModel):
    """Result of one bounded offline retrieval experiment turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: ControlledRetrievalRequest
    candidates: tuple[ControlledRetrievalCandidate, ...]
    action_rounds_used: int = Field(ge=1, le=2)
    retrieval_tokens_used: int = Field(ge=0)
    metadata_digest: Sha256String
    stop_reason: ChunkBaselineStopReason | None = None

    @model_validator(mode="after")
    def validate_empty_result(self) -> ControlledRetrievalResult:
        if not self.candidates and self.stop_reason is None:
            raise ValueError("empty retrieval requires stop_reason")
        return self


def retrieve_controlled_chunk_metadata(
    manifest: ChunkBaselineManifest,
    request: ControlledRetrievalRequest,
) -> ControlledRetrievalResult:
    """Run scope-first deterministic lexical retrieval over chunk metadata."""

    if request.turn_deadline_ms < TURN_DEADLINE_MS:
        return _empty(request, ChunkBaselineStopReason.TURN_DEADLINE, rounds=1)

    scoped: list[tuple[int, ChunkBaselineRecord]] = []
    for record in manifest.records:
        if not _matches_scope(record, request):
            continue
        score = _score(record, request)
        if score > 0:
            scoped.append((score, record))

    if len(scoped) > request.max_candidates:
        return _empty(request, ChunkBaselineStopReason.SCOPED_CANDIDATE_LIMIT, rounds=1)

    ranked = sorted(
        scoped,
        key=lambda item: (
            -item[0],
            item[1].source_id,
            item[1].page_number,
            item[1].ordinal_start,
            item[1].chunk_id,
        ),
    )
    tokens = sum(record.token_estimate for _, record in ranked)
    if tokens > request.max_retrieval_tokens:
        return _empty(
            request,
            ChunkBaselineStopReason.RETRIEVAL_TOKEN_BUDGET,
            rounds=1,
            tokens=tokens,
        )
    candidates = tuple(
        ControlledRetrievalCandidate(
            chunk_id=record.chunk_id,
            source_id=record.source_id,
            source_ref=record.source_ref,
            locator=record.locator,
            product_id=record.product_id,
            variant_id=record.variant_id,
            page_number=record.page_number,
            ordinal_start=record.ordinal_start,
            ordinal_end=record.ordinal_end,
            score=score,
            text_sha256=record.text_sha256,
            token_estimate=record.token_estimate,
        )
        for score, record in ranked
    )
    if candidates:
        return ControlledRetrievalResult(
            request=request,
            candidates=candidates,
            action_rounds_used=1,
            retrieval_tokens_used=tokens,
            metadata_digest=_digest(candidates),
        )
    return _empty(request, ChunkBaselineStopReason.NO_SCOPED_MATCH, rounds=2)


def _matches_scope(
    record: ChunkBaselineRecord,
    request: ControlledRetrievalRequest,
) -> bool:
    return (
        record.store_id == request.store_id
        and record.product_id == request.product_id
        and record.variant_id == request.variant_id
    )


def _score(record: ChunkBaselineRecord, request: ControlledRetrievalRequest) -> int:
    terms = _terms(request.query)
    if request.field_hint is not None:
        terms |= _terms(request.field_hint)
    haystack = _terms(
        " ".join(
            (
                record.chunk_id,
                record.source_id,
                record.source_ref,
                record.locator,
                *record.keywords,
            )
        )
    )
    return len(terms & haystack)


def _terms(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {term for term in normalized.split() if term}


def _empty(
    request: ControlledRetrievalRequest,
    stop_reason: ChunkBaselineStopReason,
    *,
    rounds: int,
    tokens: int = 0,
) -> ControlledRetrievalResult:
    return ControlledRetrievalResult(
        request=request,
        candidates=(),
        action_rounds_used=rounds,
        retrieval_tokens_used=tokens,
        metadata_digest=_digest(()),
        stop_reason=stop_reason,
    )


def _digest(candidates: tuple[ControlledRetrievalCandidate, ...]) -> str:
    payload = [candidate.model_dump(mode="json") for candidate in candidates]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


__all__ = [
    "MAX_ACTION_ROUNDS",
    "MAX_RETRIEVAL_TOKENS",
    "MAX_SCOPED_CANDIDATES",
    "TURN_DEADLINE_MS",
    "ControlledRetrievalCandidate",
    "ControlledRetrievalRequest",
    "ControlledRetrievalResult",
    "retrieve_controlled_chunk_metadata",
]
