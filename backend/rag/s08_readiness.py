"""S08 completion evidence for data-backed RAG readiness."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from backend.rag.corpus_readiness import (
    CorpusReadinessReport,
    CorpusReadinessStopReason,
)
from backend.rag.data_boundary import DataBoundaryReport

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

S08_MATRIX_IDS = tuple(f"S08-M{index:02d}" for index in range(1, 13))
S08_REQUIRED_OPEN_DECISIONS = (
    "OD-S08-01",
    "OD-S08-02",
    "OD-S08-03",
    "OD-S08-04",
    "OD-S08-05",
)
S08_REQUIRED_DEFERRED_CAPABILITIES = (
    "CHUNK_BASELINE_APPROVAL",
    "EMBEDDINGS",
    "INDEXES",
    "PRODUCTION_RAG_SERVING",
    "GOLDEN_SET_FREEZE",
    "TRAINING_OR_FINE_TUNING",
    "LIVE_SHOPIFY_TRUTH",
)


class S08CompletionStatus(StrEnum):
    READY_FOR_HUMAN_HANDOFF = "READY_FOR_HUMAN_HANDOFF"
    INCOMPLETE = "INCOMPLETE"


class S08MatrixEvidence(BaseModel):
    """One S08 verification matrix row and its actual evidence summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix_id: NonEmptyString
    passed: bool
    evidence: NonEmptyString


class S08ReadinessHandoff(BaseModel):
    """Internal completion handoff; not a public or client-facing contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slice_id: NonEmptyString = "S08"
    status: S08CompletionStatus
    corpus_version: NonEmptyString | None
    corpus_stop_reason: NonEmptyString
    metadata_accepted: bool
    data_boundary_accepted: bool
    matrix: tuple[S08MatrixEvidence, ...]
    open_decisions: tuple[NonEmptyString, ...] = S08_REQUIRED_OPEN_DECISIONS
    deferred_capabilities: tuple[NonEmptyString, ...] = (
        S08_REQUIRED_DEFERRED_CAPABILITIES
    )
    next_step: NonEmptyString = "Human decision on post-S08 indexing/training readiness"

    @model_validator(mode="after")
    def validate_completion_shape(self) -> S08ReadinessHandoff:
        expected_ids = set(S08_MATRIX_IDS)
        actual_ids = {item.matrix_id for item in self.matrix}
        complete = (
            actual_ids == expected_ids
            and all(item.passed for item in self.matrix)
            and self.metadata_accepted
            and self.data_boundary_accepted
            and self.corpus_stop_reason == CorpusReadinessStopReason.CORPUS_NOT_INDEXED
            and set(S08_REQUIRED_OPEN_DECISIONS).issubset(self.open_decisions)
            and set(S08_REQUIRED_DEFERRED_CAPABILITIES).issubset(
                self.deferred_capabilities
            )
        )
        if complete != (self.status is S08CompletionStatus.READY_FOR_HUMAN_HANDOFF):
            raise ValueError("S08 completion status must match evidence readiness")
        return self


def build_s08_readiness_handoff(
    *,
    corpus_report: CorpusReadinessReport,
    data_boundary_report: DataBoundaryReport,
    matrix: tuple[S08MatrixEvidence, ...],
) -> S08ReadinessHandoff:
    """Build the S08 completion handoff from existing verification evidence."""

    status = (
        S08CompletionStatus.READY_FOR_HUMAN_HANDOFF
        if _is_ready(corpus_report, data_boundary_report, matrix)
        else S08CompletionStatus.INCOMPLETE
    )
    return S08ReadinessHandoff(
        status=status,
        corpus_version=corpus_report.corpus_version,
        corpus_stop_reason=corpus_report.stop_reason.value,
        metadata_accepted=corpus_report.metadata_accepted,
        data_boundary_accepted=data_boundary_report.accepted,
        matrix=matrix,
    )


def _is_ready(
    corpus_report: CorpusReadinessReport,
    data_boundary_report: DataBoundaryReport,
    matrix: tuple[S08MatrixEvidence, ...],
) -> bool:
    return (
        corpus_report.metadata_accepted
        and corpus_report.stop_reason is CorpusReadinessStopReason.CORPUS_NOT_INDEXED
        and data_boundary_report.accepted
        and {item.matrix_id for item in matrix} == set(S08_MATRIX_IDS)
        and all(item.passed for item in matrix)
    )


__all__ = [
    "S08_MATRIX_IDS",
    "S08_REQUIRED_DEFERRED_CAPABILITIES",
    "S08_REQUIRED_OPEN_DECISIONS",
    "S08CompletionStatus",
    "S08MatrixEvidence",
    "S08ReadinessHandoff",
    "build_s08_readiness_handoff",
]
