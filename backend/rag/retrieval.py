"""Metadata-filtered baseline retrieval for Slice 5 Product RAG."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.common import ObjectScope
from backend.rag.manifest import DocumentChunk

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class RetrievalModel(BaseModel):
    """Strict internal retrieval model; not a public wire contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class RetrievalStrategy(StrEnum):
    KEYWORD_OVERLAP = "KEYWORD_OVERLAP"


class RetrievalRequest(RetrievalModel):
    turn_target: ObjectScope
    question: NonEmptyString
    k: int = Field(default=3, ge=1, le=10)
    field_hint: NonEmptyString | None = None
    max_retrieval_tokens: int = Field(default=4000, ge=1)


class RetrievalResult(RetrievalModel):
    request: RetrievalRequest
    evidence: tuple[DocumentChunk, ...]
    retrieval_strategy: RetrievalStrategy
    index_version: NonEmptyString
    filtered_out_count: int = Field(ge=0)
    missing_reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "RetrievalResult":
        if not self.evidence and self.missing_reason is None:
            raise ValueError("empty retrieval results require missing_reason")
        return self


class InMemoryProductRetriever:
    """Deterministic local retriever that filters metadata before ranking."""

    def __init__(
        self,
        chunks: tuple[DocumentChunk, ...],
        *,
        index_version: str,
    ) -> None:
        self._chunks = tuple(chunks)
        self._index_version = index_version

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        scoped_chunks: list[DocumentChunk] = []
        filtered_out_count = 0
        for chunk in self._chunks:
            if _matches_scope(chunk, request.turn_target):
                scoped_chunks.append(chunk)
            else:
                filtered_out_count += 1

        ranked = sorted(
            (
                (_score_chunk(chunk, request), chunk.order, chunk)
                for chunk in scoped_chunks
            ),
            key=lambda item: (-item[0], item[1]),
        )
        selected = tuple(chunk for score, _, chunk in ranked if score > 0)[: request.k]
        missing_reason = None if selected else "NO_SCOPED_MATCH"
        return RetrievalResult(
            request=request,
            evidence=selected,
            retrieval_strategy=RetrievalStrategy.KEYWORD_OVERLAP,
            index_version=self._index_version,
            filtered_out_count=filtered_out_count,
            missing_reason=missing_reason,
        )


def _matches_scope(chunk: DocumentChunk, scope: ObjectScope) -> bool:
    if chunk.store_id != scope.store_id or chunk.product_id != scope.product_id:
        return False
    if scope.variant_id is None:
        return chunk.variant_id is None
    return chunk.variant_id in (None, scope.variant_id)


def _score_chunk(chunk: DocumentChunk, request: RetrievalRequest) -> int:
    query_terms = _terms(request.question)
    if request.field_hint is not None:
        query_terms |= _terms(request.field_hint)
    chunk_terms = _terms(" ".join((*chunk.heading_path, chunk.text)))
    return len(query_terms & chunk_terms)


def _terms(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {term for term in normalized.split() if term}
