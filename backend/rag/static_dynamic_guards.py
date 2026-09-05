"""Internal S08 guards for static RAG versus dynamic or stale data."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

CURRENT_CORPUS_VERSION = "v0.1"
APPROVED_CHUNK_BASELINE_STATUS = "HUMAN_DECISION_ACCEPTED__CHUNK_BASELINE_ALLOWED"
SHOPIFY_CANDIDATE_STATUS = "CANDIDATE_WITH_LIMITATIONS"
SHOPIFY_VARIANT_UNRESOLVED_STATUS = "UNRESOLVED_FROM_STANDARD_EXPORT"
DYNAMIC_COMMERCE_TERMS = (
    "price",
    "inventory",
    "availability",
    "available",
    "in stock",
    "sale",
    "sellable",
    "current",
    "now",
    "today",
    "价格",
    "库存",
    "有货",
    "现货",
    "可售",
    "当前",
    "今天",
    "多少钱",
)


class StaticRagStopReason(StrEnum):
    DYNAMIC_FACT_REQUIRED = "DYNAMIC_FACT_REQUIRED"
    CORPUS_VERSION_MISMATCH = "CORPUS_VERSION_MISMATCH"
    CHUNK_BASELINE_MANIFEST_MISSING = "CHUNK_BASELINE_MANIFEST_MISSING"
    CHUNK_BASELINE_NEEDS_CHANGES = "CHUNK_BASELINE_NEEDS_CHANGES"
    SHOPIFY_CANDIDATE_LIMITATION = "SHOPIFY_CANDIDATE_LIMITATION"
    GOLDEN_SET_NOT_FROZEN = "GOLDEN_SET_NOT_FROZEN"
    TRAINING_NOT_AUTHORIZED = "TRAINING_NOT_AUTHORIZED"


class ChunkBaselineState(BaseModel):
    """Review state for a candidate chunk baseline, without chunk text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_present: bool
    review_status: NonEmptyString | None = None


class ShopifyCandidateSnapshotState(BaseModel):
    """Read-only status of a candidate Shopify snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: NonEmptyString
    variant_id_status: NonEmptyString
    used_as_current_truth: bool = False


class StaticRagPreflightRequest(BaseModel):
    """Internal preflight inputs before static RAG evidence can be used."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: NonEmptyString
    corpus_version: NonEmptyString = CURRENT_CORPUS_VERSION
    expected_corpus_version: NonEmptyString = CURRENT_CORPUS_VERSION
    chunk_baseline: ChunkBaselineState | None = None
    shopify_snapshot: ShopifyCandidateSnapshotState | None = None
    golden_set_frozen: bool = True
    training_requested: bool = False


class StaticRagPreflightReport(BaseModel):
    """Fail-closed guard result; not a public wire contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    stop_reason: StaticRagStopReason | None = None

    @model_validator(mode="after")
    def validate_report_shape(self) -> StaticRagPreflightReport:
        if self.accepted == (self.stop_reason is not None):
            raise ValueError("accepted reports must not carry stop_reason")
        return self


def evaluate_static_rag_preflight(
    request: StaticRagPreflightRequest,
) -> StaticRagPreflightReport:
    """Return the first exact guard reason before static RAG can proceed."""

    if is_dynamic_commerce_question(request.question):
        return _stop(StaticRagStopReason.DYNAMIC_FACT_REQUIRED)
    if request.corpus_version != request.expected_corpus_version:
        return _stop(StaticRagStopReason.CORPUS_VERSION_MISMATCH)
    if request.chunk_baseline is not None:
        if not request.chunk_baseline.manifest_present:
            return _stop(StaticRagStopReason.CHUNK_BASELINE_MANIFEST_MISSING)
        if request.chunk_baseline.review_status != APPROVED_CHUNK_BASELINE_STATUS:
            return _stop(StaticRagStopReason.CHUNK_BASELINE_NEEDS_CHANGES)
    if _shopify_candidate_used_as_truth(request.shopify_snapshot):
        return _stop(StaticRagStopReason.SHOPIFY_CANDIDATE_LIMITATION)
    if not request.golden_set_frozen:
        return _stop(StaticRagStopReason.GOLDEN_SET_NOT_FROZEN)
    if request.training_requested:
        return _stop(StaticRagStopReason.TRAINING_NOT_AUTHORIZED)
    return StaticRagPreflightReport(accepted=True)


def is_dynamic_commerce_question(text: str) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in DYNAMIC_COMMERCE_TERMS)


def _shopify_candidate_used_as_truth(
    snapshot: ShopifyCandidateSnapshotState | None,
) -> bool:
    if snapshot is None or not snapshot.used_as_current_truth:
        return False
    return (
        snapshot.status == SHOPIFY_CANDIDATE_STATUS
        or snapshot.variant_id_status == SHOPIFY_VARIANT_UNRESOLVED_STATUS
    )


def _stop(reason: StaticRagStopReason) -> StaticRagPreflightReport:
    return StaticRagPreflightReport(accepted=False, stop_reason=reason)


__all__ = [
    "APPROVED_CHUNK_BASELINE_STATUS",
    "CURRENT_CORPUS_VERSION",
    "DYNAMIC_COMMERCE_TERMS",
    "SHOPIFY_CANDIDATE_STATUS",
    "SHOPIFY_VARIANT_UNRESOLVED_STATUS",
    "ChunkBaselineState",
    "ShopifyCandidateSnapshotState",
    "StaticRagPreflightReport",
    "StaticRagPreflightRequest",
    "StaticRagStopReason",
    "evaluate_static_rag_preflight",
    "is_dynamic_commerce_question",
]
