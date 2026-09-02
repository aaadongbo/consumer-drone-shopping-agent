"""Internal adapters from baseline retrieval results to Evidence checks."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.rag.manifest import DocumentChunk
from backend.rag.retrieval import (
    RetrievalRequest,
    RetrievalResult,
    RetrievalStrategy,
)

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class RetrievalEvidenceBundle(BaseModel):
    """Stable internal view consumed by the Slice 5 Evidence Gate.

    The adapter deliberately keeps the original request and retrieval metadata
    alongside the chunks.  This prevents a later gate from losing the target or
    index version while converting the retrieval result into Evidence input.
    It is internal and does not change the public response contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: RetrievalRequest
    evidence: tuple[DocumentChunk, ...]
    retrieval_strategy: RetrievalStrategy
    index_version: NonEmptyString
    filtered_out_count: int = Field(ge=0)
    missing_reason: NonEmptyString | None = None

    @classmethod
    def from_result(cls, result: RetrievalResult) -> RetrievalEvidenceBundle:
        """Adapt one typed RetrievalResult without changing any values."""
        return cls.model_validate(result.model_dump())

    def to_result(self) -> RetrievalResult:
        """Rebuild the existing retrieval type for downstream replay."""
        return RetrievalResult.model_validate(self.model_dump())

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


RetrievalResultAdapter = RetrievalEvidenceBundle


def adapt_retrieval_result(
    result: RetrievalResult | RetrievalEvidenceBundle,
) -> RetrievalEvidenceBundle:
    """Return a lossless Evidence-facing view of a retrieval result."""
    if isinstance(result, RetrievalEvidenceBundle):
        return result
    if isinstance(result, RetrievalResult):
        return RetrievalEvidenceBundle.from_result(result)
    raise TypeError("Expected RetrievalResult or RetrievalEvidenceBundle")


__all__ = [
    "RetrievalEvidenceBundle",
    "RetrievalResultAdapter",
    "adapt_retrieval_result",
]
