"""Offline S08 metadata-only retrieval skeleton over scoped locator records."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.rag.locator_binding import (
    LocatorBinding,
    LocatorBindingSource,
    Mavic3ScopeOverlay,
    bind_locator_record,
)
from backend.rag.retrieval import RetrievalRequest, RetrievalStrategy
from backend.rag.static_dynamic_guards import (
    StaticRagStopReason,
    is_dynamic_commerce_question,
)

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

DEFAULT_MAX_SCOPED_CANDIDATES = 10
NO_SCOPED_MATCH = "NO_SCOPED_MATCH"
CORPUS_NOT_INDEXED = "CORPUS_NOT_INDEXED"
SCOPED_CANDIDATE_LIMIT = "SCOPED_CANDIDATE_LIMIT"
DYNAMIC_FACT_REQUIRED = StaticRagStopReason.DYNAMIC_FACT_REQUIRED.value


class OfflineLocatorRecord(BaseModel):
    """One metadata-only locator candidate plus expected source binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record: dict[str, Any]
    source: LocatorBindingSource
    keywords: tuple[NonEmptyString, ...] = ()


class OfflineLocatorRetrievalResult(BaseModel):
    """Internal retrieval skeleton result for locator candidates only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: RetrievalRequest
    candidate_locators: tuple[LocatorBinding, ...]
    retrieval_strategy: RetrievalStrategy
    index_version: NonEmptyString
    filtered_out_count: int = Field(ge=0)
    missing_reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> OfflineLocatorRetrievalResult:
        if not self.candidate_locators and self.missing_reason is None:
            raise ValueError("empty locator retrieval results require missing_reason")
        return self


class OfflineMetadataLocatorRetriever:
    """Deterministic scope-first retriever for staged locator metadata."""

    def __init__(
        self,
        records: tuple[OfflineLocatorRecord, ...],
        *,
        index_version: str,
        overlays: tuple[Mavic3ScopeOverlay, ...] = (),
        corpus_indexed: bool = True,
        max_scoped_candidates: int = DEFAULT_MAX_SCOPED_CANDIDATES,
    ) -> None:
        if max_scoped_candidates < 1:
            raise ValueError("max_scoped_candidates must be at least 1")
        self._records = records
        self._index_version = index_version
        self._overlays = {overlay.source_id: overlay for overlay in overlays}
        self._corpus_indexed = corpus_indexed
        self._max_scoped_candidates = max_scoped_candidates

    def retrieve(self, request: RetrievalRequest) -> OfflineLocatorRetrievalResult:
        if is_dynamic_commerce_question(request.question):
            return self._missing(
                request,
                filtered_out_count=0,
                missing_reason=DYNAMIC_FACT_REQUIRED,
            )

        scoped: list[tuple[int, LocatorBinding]] = []
        filtered_out_count = 0
        for candidate in self._records:
            result = bind_locator_record(
                candidate.record,
                target_scope=request.turn_target,
                source=candidate.source,
                overlay=self._overlays.get(candidate.source.source_id),
            )
            if not result.accepted:
                filtered_out_count += 1
                continue
            assert result.binding is not None
            score = _score_candidate(result.binding, candidate, request)
            if score <= 0:
                filtered_out_count += 1
                continue
            scoped.append((score, result.binding))

        if len(scoped) > self._max_scoped_candidates:
            return self._missing(
                request,
                filtered_out_count=filtered_out_count,
                missing_reason=SCOPED_CANDIDATE_LIMIT,
            )

        ranked = sorted(
            scoped,
            key=lambda item: (-item[0], item[1].source_id, item[1].page_number),
        )
        selected = tuple(binding for _, binding in ranked[: request.k])
        if selected:
            return OfflineLocatorRetrievalResult(
                request=request,
                candidate_locators=selected,
                retrieval_strategy=RetrievalStrategy.KEYWORD_OVERLAP,
                index_version=self._index_version,
                filtered_out_count=filtered_out_count,
            )

        missing_reason = NO_SCOPED_MATCH if self._corpus_indexed else CORPUS_NOT_INDEXED
        return self._missing(
            request,
            filtered_out_count=filtered_out_count,
            missing_reason=missing_reason,
        )

    def _missing(
        self,
        request: RetrievalRequest,
        *,
        filtered_out_count: int,
        missing_reason: str,
    ) -> OfflineLocatorRetrievalResult:
        return OfflineLocatorRetrievalResult(
            request=request,
            candidate_locators=(),
            retrieval_strategy=RetrievalStrategy.KEYWORD_OVERLAP,
            index_version=self._index_version,
            filtered_out_count=filtered_out_count,
            missing_reason=missing_reason,
        )


def _score_candidate(
    binding: LocatorBinding,
    candidate: OfflineLocatorRecord,
    request: RetrievalRequest,
) -> int:
    query_terms = _terms(request.question)
    if request.field_hint is not None:
        query_terms |= _terms(request.field_hint)
    metadata_terms = _terms(
        " ".join(
            (
                binding.source_ref,
                binding.source_id,
                binding.product_scope,
                binding.locator,
                *candidate.keywords,
            )
        )
    )
    return len(query_terms & metadata_terms)


def _terms(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {term for term in normalized.split() if term}


__all__ = [
    "CORPUS_NOT_INDEXED",
    "DEFAULT_MAX_SCOPED_CANDIDATES",
    "DYNAMIC_FACT_REQUIRED",
    "NO_SCOPED_MATCH",
    "SCOPED_CANDIDATE_LIMIT",
    "OfflineLocatorRecord",
    "OfflineLocatorRetrievalResult",
    "OfflineMetadataLocatorRetriever",
]
