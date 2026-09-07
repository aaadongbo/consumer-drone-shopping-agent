"""Internal, scope-first BM25 baseline for offline retrieval evaluation.

The index is ephemeral and accepts caller-supplied documents. It never reads
Shopify, persists source text, or changes the public retrieval contract.
"""

from __future__ import annotations

import math
import re
import unicodedata
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.common import ObjectScope
from backend.rag.static_dynamic_guards import is_dynamic_commerce_question

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
type Sha256String = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

MAX_ACTION_ROUNDS = 2
MAX_TOOL_CALLS = 2
MAX_RETRIEVAL_TOKENS = 4000
MAX_MODEL_TOKENS = 1200
TURN_DEADLINE_MS = 8000
MAX_SCOPED_CANDIDATES = 10


class Bm25StopReason(StrEnum):
    """Fail-closed reasons for a bounded BM25 turn."""

    DYNAMIC_FACT_REQUIRED = "DYNAMIC_FACT_REQUIRED"
    NO_SCOPED_MATCH = "NO_SCOPED_MATCH"
    SCOPED_CANDIDATE_LIMIT = "SCOPED_CANDIDATE_LIMIT"
    RETRIEVAL_TOKEN_BUDGET = "RETRIEVAL_TOKEN_BUDGET"
    TURN_DEADLINE = "TURN_DEADLINE"


class Bm25Document(BaseModel):
    """One ephemeral document with source provenance and exact object scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: NonEmptyString
    text: NonEmptyString
    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    source_id: NonEmptyString
    source_version: NonEmptyString
    locator: NonEmptyString
    text_sha256: Sha256String
    page_number: int = Field(ge=1)
    token_estimate: int = Field(ge=1)


class Bm25Request(BaseModel):
    """Internal request with the existing retrieval hard limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_target: ObjectScope
    query: NonEmptyString
    k: int = Field(default=3, ge=1, le=MAX_SCOPED_CANDIDATES)
    field_hint: NonEmptyString | None = None
    candidate_cap: int = Field(default=MAX_SCOPED_CANDIDATES, ge=1, le=10)
    max_retrieval_tokens: int = Field(
        default=MAX_RETRIEVAL_TOKENS, ge=1, le=MAX_RETRIEVAL_TOKENS
    )
    turn_deadline_ms: int = Field(default=TURN_DEADLINE_MS, ge=1, le=TURN_DEADLINE_MS)


class Bm25Candidate(BaseModel):
    """Ranked metadata-only result; source text is never returned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: NonEmptyString
    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    source_id: NonEmptyString
    source_version: NonEmptyString
    locator: NonEmptyString
    text_sha256: Sha256String
    page_number: int = Field(ge=1)
    score: float = Field(ge=0)
    rank: int = Field(ge=1)
    token_estimate: int = Field(ge=1)


class Bm25Result(BaseModel):
    """Bounded BM25 output with provenance and stop metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: Bm25Request
    index_version: NonEmptyString
    candidates: tuple[Bm25Candidate, ...]
    filtered_out_count: int = Field(ge=0)
    retrieval_tokens_used: int = Field(ge=0)
    stop_reason: Bm25StopReason | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> Bm25Result:
        if not self.candidates and self.stop_reason is None:
            raise ValueError("empty BM25 results require stop_reason")
        if self.candidates and self.stop_reason not in (
            None,
            Bm25StopReason.SCOPED_CANDIDATE_LIMIT,
            Bm25StopReason.RETRIEVAL_TOKEN_BUDGET,
        ):
            raise ValueError("non-empty BM25 results cannot carry stop_reason")
        return self


class Bm25Index:
    """Deterministic in-memory BM25 index with metadata-first filtering."""

    def __init__(
        self,
        documents: tuple[Bm25Document, ...],
        *,
        index_version: str,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        if not documents:
            raise ValueError("BM25 index requires at least one document")
        if not index_version.strip():
            raise ValueError("index_version must not be empty")
        if k1 <= 0 or b < 0 or b > 1:
            raise ValueError("BM25 parameters must satisfy k1 > 0 and 0 <= b <= 1")
        document_ids = [document.document_id for document in documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("BM25 document_id values must be unique")
        self._documents = documents
        self._index_version = index_version
        self._k1 = k1
        self._b = b
        self._terms = tuple(
            tuple(tokenize_bm25(document.text)) for document in documents
        )
        self._document_frequency: dict[str, int] = {}
        for terms in self._terms:
            for term in set(terms):
                self._document_frequency[term] = (
                    self._document_frequency.get(term, 0) + 1
                )
        self._average_document_length = sum(map(len, self._terms)) / len(self._terms)

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def search(self, request: Bm25Request) -> Bm25Result:
        if request.turn_deadline_ms < TURN_DEADLINE_MS:
            return self._empty(request, Bm25StopReason.TURN_DEADLINE)
        if is_dynamic_commerce_question(request.query):
            return self._empty(request, Bm25StopReason.DYNAMIC_FACT_REQUIRED)

        query_terms = list(tokenize_bm25(request.query))
        if request.field_hint is not None:
            query_terms.extend(tokenize_bm25(request.field_hint))
        query_terms = tuple(query_terms)
        if not query_terms:
            return self._empty(request, Bm25StopReason.NO_SCOPED_MATCH)

        scoped: list[tuple[float, Bm25Document, int]] = []
        filtered_out_count = 0
        for document, terms in zip(self._documents, self._terms, strict=True):
            if not _matches_scope(document, request.turn_target):
                filtered_out_count += 1
                continue
            score = _bm25_score(
                query_terms,
                terms,
                self._document_frequency,
                self.document_count,
                self._average_document_length,
                self._k1,
                self._b,
            )
            if score > 0:
                scoped.append((score, document, len(terms)))

        if not scoped:
            return self._empty(
                request,
                Bm25StopReason.NO_SCOPED_MATCH,
                filtered_out_count=filtered_out_count,
            )
        ranked = sorted(
            scoped,
            key=lambda item: (
                -item[0],
                item[1].source_id,
                item[1].page_number,
                item[1].document_id,
            ),
        )
        candidate_limit_hit = len(ranked) > request.candidate_cap
        bounded = ranked[: min(request.k, request.candidate_cap)]
        selected: list[tuple[float, Bm25Document, int]] = []
        retrieval_tokens = 0
        budget_hit = False
        for item in bounded:
            item_tokens = item[1].token_estimate
            if retrieval_tokens + item_tokens > request.max_retrieval_tokens:
                budget_hit = True
                break
            selected.append(item)
            retrieval_tokens += item_tokens
        if not selected:
            return self._empty(
                request,
                Bm25StopReason.RETRIEVAL_TOKEN_BUDGET,
                filtered_out_count=filtered_out_count,
                retrieval_tokens_used=bounded[0][1].token_estimate,
            )
        candidates = tuple(
            Bm25Candidate(
                document_id=document.document_id,
                store_id=document.store_id,
                product_id=document.product_id,
                variant_id=document.variant_id,
                source_id=document.source_id,
                source_version=document.source_version,
                locator=document.locator,
                text_sha256=document.text_sha256,
                page_number=document.page_number,
                score=score,
                rank=rank,
                token_estimate=document.token_estimate,
            )
            for rank, (score, document, _) in enumerate(selected, 1)
        )
        return Bm25Result(
            request=request,
            index_version=self._index_version,
            candidates=candidates,
            filtered_out_count=filtered_out_count,
            retrieval_tokens_used=retrieval_tokens,
            stop_reason=(
                Bm25StopReason.RETRIEVAL_TOKEN_BUDGET
                if budget_hit
                else Bm25StopReason.SCOPED_CANDIDATE_LIMIT
                if candidate_limit_hit
                else None
            ),
        )

    def _empty(
        self,
        request: Bm25Request,
        reason: Bm25StopReason,
        *,
        filtered_out_count: int = 0,
        retrieval_tokens_used: int = 0,
    ) -> Bm25Result:
        return Bm25Result(
            request=request,
            index_version=self._index_version,
            candidates=(),
            filtered_out_count=filtered_out_count,
            retrieval_tokens_used=retrieval_tokens_used,
            stop_reason=reason,
        )


def tokenize_bm25(text: str) -> tuple[str, ...]:
    """Tokenize Latin/numeric runs and CJK unigrams/bigrams deterministically."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    for match in re.finditer(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized):
        segment = match.group(0)
        if all("\u4e00" <= char <= "\u9fff" for char in segment):
            tokens.extend(segment)
            tokens.extend(
                segment[index : index + 2] for index in range(len(segment) - 1)
            )
        else:
            tokens.append(segment)
    return tuple(tokens)


def _matches_scope(document: Bm25Document, scope: ObjectScope) -> bool:
    if document.store_id != scope.store_id or document.product_id != scope.product_id:
        return False
    if scope.variant_id is None:
        return document.variant_id is None
    return document.variant_id in (None, scope.variant_id)


def _bm25_score(
    query_terms: tuple[str, ...],
    document_terms: tuple[str, ...],
    document_frequency: dict[str, int],
    document_count: int,
    average_document_length: float,
    k1: float,
    b: float,
) -> float:
    frequencies: dict[str, int] = {}
    for term in document_terms:
        frequencies[term] = frequencies.get(term, 0) + 1
    length = len(document_terms)
    score = 0.0
    for term in set(query_terms):
        frequency = frequencies.get(term, 0)
        if frequency == 0:
            continue
        df = document_frequency.get(term, 0)
        idf = math.log1p((document_count - df + 0.5) / (df + 0.5))
        denominator = frequency + k1 * (
            1 - b + b * length / max(average_document_length, 1)
        )
        score += idf * (frequency * (k1 + 1)) / denominator
    return score


__all__ = [
    "Bm25Candidate",
    "Bm25Document",
    "Bm25Index",
    "Bm25Request",
    "Bm25Result",
    "Bm25StopReason",
    "MAX_ACTION_ROUNDS",
    "MAX_MODEL_TOKENS",
    "MAX_RETRIEVAL_TOKENS",
    "MAX_SCOPED_CANDIDATES",
    "MAX_TOOL_CALLS",
    "TURN_DEADLINE_MS",
    "tokenize_bm25",
]
