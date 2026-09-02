"""Evidence-covered recommendation explanations and degradation semantics."""

from enum import StrEnum

from pydantic import Field

from backend.common import AttributeStatus
from backend.common.contracts import WireModel
from backend.evidence import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    DerivedEvidence,
)


class RecommendationFallbackReason(StrEnum):
    """Stable internal reasons for degrading recommendation explanations."""

    NO_MATCH = "NO_MATCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    COMMERCE_REFRESH_FAILED = "COMMERCE_REFRESH_FAILED"
    RAG_UNAVAILABLE = "RAG_UNAVAILABLE"
    COVERAGE_BELOW_THRESHOLD = "COVERAGE_BELOW_THRESHOLD"


class SupportedReason(WireModel):
    """One deterministic reason bound to one candidate evidence ID."""

    candidate: CandidateIdentity
    field: str
    text: str = Field(min_length=1)
    evidence_id: str


class RecommendationExplanation(WireModel):
    """Internal explanation with explicit reason and derived-evidence bindings."""

    candidate: CandidateIdentity
    supported_reasons: tuple[SupportedReason, ...] = ()
    tradeoffs: tuple[DerivedEvidence, ...] = ()
    unknown_dimensions: tuple[str, ...] = ()
    binding_map: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class RecommendationFallback(WireModel):
    """Internal fail-closed recommendation degradation result."""

    reason: RecommendationFallbackReason
    candidate: CandidateIdentity | None = None
    missing_fields: tuple[str, ...] = ()
    message: str = Field(min_length=1)


class RecommendationExplanationResult(WireModel):
    """Either an evidence-backed explanation or a safe degradation."""

    explanation: RecommendationExplanation | None = None
    fallback: RecommendationFallback | None = None


def build_recommendation_explanation(
    bundle: CandidateEvidenceBundle,
    *,
    requested_fields: tuple[str, ...],
    critical_fields: tuple[str, ...] = (),
    tradeoffs: tuple[DerivedEvidence, ...] = (),
) -> RecommendationExplanationResult:
    """Build only reasons covered by this candidate's own evidence bundle."""

    evidence_by_field: dict[str, CandidateEvidence] = {}
    for evidence in (
        *bundle.catalog_evidence,
        *bundle.commerce_evidence,
        *bundle.rag_evidence,
    ):
        evidence_by_field.setdefault(evidence.field, evidence)

    reasons: list[SupportedReason] = []
    unknown: list[str] = []
    missing: list[str] = []
    bindings: dict[str, tuple[str, ...]] = {}
    for field in requested_fields:
        evidence = evidence_by_field.get(field)
        if evidence is None:
            missing.append(field)
            continue
        if (
            evidence.fact is not None
            and evidence.fact.status is not AttributeStatus.KNOWN
        ):
            unknown.append(field)
            continue
        reason_text = evidence.text
        if reason_text is None and evidence.fact is not None:
            reason_text = f"{field}={evidence.fact.value}"
        if reason_text is None:
            missing.append(field)
            continue
        reason = SupportedReason(
            candidate=bundle.candidate,
            field=field,
            text=reason_text,
            evidence_id=evidence.evidence_id,
        )
        reasons.append(reason)
        bindings[field] = (evidence.evidence_id,)

    if any(item.candidate != bundle.candidate for item in tradeoffs):
        raise ValueError("tradeoff evidence crossed candidate identity")
    critical_missing = tuple(field for field in critical_fields if field in missing)
    if critical_missing:
        return RecommendationExplanationResult(
            fallback=RecommendationFallback(
                reason=RecommendationFallbackReason.COVERAGE_BELOW_THRESHOLD,
                candidate=bundle.candidate,
                missing_fields=critical_missing,
                message="Critical recommendation evidence is unavailable.",
            )
        )
    if not reasons and not unknown:
        return RecommendationExplanationResult(
            fallback=RecommendationFallback(
                reason=RecommendationFallbackReason.INSUFFICIENT_EVIDENCE,
                candidate=bundle.candidate,
                missing_fields=tuple(missing),
                message="Recommendation evidence is insufficient.",
            )
        )
    return RecommendationExplanationResult(
        explanation=RecommendationExplanation(
            candidate=bundle.candidate,
            supported_reasons=tuple(reasons),
            tradeoffs=tradeoffs,
            unknown_dimensions=tuple(unknown),
            binding_map=bindings,
        )
    )


__all__ = [
    "RecommendationExplanation",
    "RecommendationExplanationResult",
    "RecommendationFallback",
    "RecommendationFallbackReason",
    "SupportedReason",
    "build_recommendation_explanation",
]
