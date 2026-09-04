"""S09 development-only replay and readiness handoff."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.rag.chunk_baseline import ChunkBaselineManifest, ChunkBaselineStopReason
from backend.rag.controlled_retrieval import (
    ControlledRetrievalRequest,
    ControlledRetrievalResult,
    retrieve_controlled_chunk_metadata,
)

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

S09_MATRIX_IDS = tuple(f"S09-M{index:02d}" for index in range(1, 10))
S09_DEFERRED_CAPABILITIES = (
    "PRODUCTION_INDEX",
    "EMBEDDINGS",
    "RERANKER",
    "GOLDEN_SET_FREEZE",
    "TRAINING_OR_FINE_TUNING",
    "LIVE_SHOPIFY_TRUTH",
)


class S09HandoffDecision(StrEnum):
    GO = "GO"
    HOLD = "HOLD"


class DevelopmentReplayCase(BaseModel):
    """One non-frozen development replay case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: NonEmptyString
    request: ControlledRetrievalRequest
    expected_locator: NonEmptyString | None = None


class DevelopmentReplayResult(BaseModel):
    """Development-only metric row for controlled retrieval readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: NonEmptyString
    passed: bool
    retrieved_count: int = Field(ge=0)
    stop_reason: ChunkBaselineStopReason | None = None
    development_only: bool = True


class DevelopmentReplayReport(BaseModel):
    """Aggregate development replay report. It cannot freeze a Golden Set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: int = Field(ge=0, le=15)
    passed_count: int = Field(ge=0)
    development_only: bool = True
    golden_set_frozen: bool = False
    results: tuple[DevelopmentReplayResult, ...]

    @model_validator(mode="after")
    def validate_counts(self) -> DevelopmentReplayReport:
        if self.case_count != len(self.results):
            raise ValueError("case_count must match results")
        if self.passed_count != sum(1 for result in self.results if result.passed):
            raise ValueError("passed_count must match passing results")
        if not self.development_only or self.golden_set_frozen:
            raise ValueError("S09 replay must remain development-only")
        return self


class S09ReadinessHandoff(BaseModel):
    """Final metadata-only handoff for a later production-index decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slice_id: NonEmptyString = "S09"
    decision: S09HandoffDecision
    reason: NonEmptyString
    chunk_baseline_accepted: bool
    retrieval_replay_passed: bool
    data_boundary_accepted: bool
    matrix_ids: tuple[NonEmptyString, ...]
    deferred_capabilities: tuple[NonEmptyString, ...] = S09_DEFERRED_CAPABILITIES
    claims_production_ready: bool = False

    @model_validator(mode="after")
    def validate_handoff(self) -> S09ReadinessHandoff:
        if self.claims_production_ready:
            raise ValueError("S09 cannot claim production readiness")
        ready = (
            self.chunk_baseline_accepted
            and self.retrieval_replay_passed
            and self.data_boundary_accepted
            and set(self.matrix_ids) == set(S09_MATRIX_IDS)
        )
        if ready != (self.decision is S09HandoffDecision.GO):
            raise ValueError("handoff decision must match readiness evidence")
        return self


def replay_development_cases(
    manifest: ChunkBaselineManifest,
    cases: tuple[DevelopmentReplayCase, ...],
) -> DevelopmentReplayReport:
    """Replay at most 15 development cases against the in-memory experiment."""

    if len(cases) > 15:
        raise ValueError("S09 development replay is limited to 15 cases")
    results: list[DevelopmentReplayResult] = []
    for case in cases:
        retrieval = retrieve_controlled_chunk_metadata(manifest, case.request)
        results.append(_result_for_case(case, retrieval))
    return DevelopmentReplayReport(
        case_count=len(results),
        passed_count=sum(1 for result in results if result.passed),
        results=tuple(results),
    )


def build_s09_readiness_handoff(
    *,
    chunk_baseline_accepted: bool,
    replay_report: DevelopmentReplayReport,
    data_boundary_accepted: bool,
    matrix_ids: tuple[str, ...] = S09_MATRIX_IDS,
) -> S09ReadinessHandoff:
    """Build a GO/HOLD handoff without claiming Human or production approval."""

    replay_passed = bool(replay_report.results) and all(
        result.passed for result in replay_report.results
    )
    decision = (
        S09HandoffDecision.GO
        if chunk_baseline_accepted and replay_passed and data_boundary_accepted
        else S09HandoffDecision.HOLD
    )
    reason = (
        "controlled retrieval experiment complete"
        if decision is S09HandoffDecision.GO
        else "readiness evidence incomplete"
    )
    return S09ReadinessHandoff(
        decision=decision,
        reason=reason,
        chunk_baseline_accepted=chunk_baseline_accepted,
        retrieval_replay_passed=replay_passed,
        data_boundary_accepted=data_boundary_accepted,
        matrix_ids=tuple(matrix_ids),
    )


def _result_for_case(
    case: DevelopmentReplayCase,
    retrieval: ControlledRetrievalResult,
) -> DevelopmentReplayResult:
    locators = {candidate.locator for candidate in retrieval.candidates}
    passed = (
        case.expected_locator in locators
        if case.expected_locator is not None
        else retrieval.stop_reason is not None
    )
    return DevelopmentReplayResult(
        case_id=case.case_id,
        passed=passed,
        retrieved_count=len(retrieval.candidates),
        stop_reason=retrieval.stop_reason,
    )


__all__ = [
    "S09_DEFERRED_CAPABILITIES",
    "S09_MATRIX_IDS",
    "DevelopmentReplayCase",
    "DevelopmentReplayReport",
    "DevelopmentReplayResult",
    "S09HandoffDecision",
    "S09ReadinessHandoff",
    "build_s09_readiness_handoff",
    "replay_development_cases",
]
