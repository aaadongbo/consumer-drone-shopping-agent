"""Evidence helpers for recommendation assembly and Product RAG gates."""

from backend.evidence.commerce import build_commerce_evidence
from backend.evidence.comparison import (
    ComparisonDegradationReason,
    ComparisonEvidenceBinding,
    ComparisonFact,
    ComparisonFactSet,
    ComparisonFactState,
    ComparisonFreshness,
    ComparisonFreshnessVerdict,
    build_dynamic_comparison_facts,
    build_static_comparison_facts,
    read_dynamic_comparison_facts,
)
from backend.evidence.derived import (
    derive_budget_margin,
    derive_numeric_delta,
    validate_derived_inputs,
)
from backend.evidence.rag_quality import (
    EvidenceGateResult,
    EvidenceQuality,
    EvidenceQualityVerdict,
    RagClaim,
    RagFallback,
    RagFallbackReason,
    gate_retrieval_evidence,
    reject_for_budget,
)
from backend.evidence.recommendation import (
    RecommendationCandidate,
    RecommendationCandidateSet,
    RecommendationReason,
    build_recommendation_candidates,
)
from backend.evidence.recommendation_bundle import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    CoverageStatus,
    DerivedEvidence,
    EvidenceCoverage,
    EvidenceSourceKind,
    candidate_scope,
)

__all__ = [
    "ComparisonDegradationReason",
    "ComparisonEvidenceBinding",
    "ComparisonFact",
    "ComparisonFactState",
    "ComparisonFactSet",
    "ComparisonFreshness",
    "ComparisonFreshnessVerdict",
    "EvidenceGateResult",
    "EvidenceQuality",
    "EvidenceQualityVerdict",
    "RagClaim",
    "RagFallback",
    "RagFallbackReason",
    "RecommendationCandidate",
    "RecommendationCandidateSet",
    "RecommendationReason",
    "CandidateEvidence",
    "CandidateEvidenceBundle",
    "CandidateIdentity",
    "CoverageStatus",
    "DerivedEvidence",
    "EvidenceCoverage",
    "EvidenceSourceKind",
    "build_dynamic_comparison_facts",
    "build_static_comparison_facts",
    "build_recommendation_candidates",
    "read_dynamic_comparison_facts",
    "gate_retrieval_evidence",
    "reject_for_budget",
    "candidate_scope",
    "build_commerce_evidence",
    "derive_budget_margin",
    "derive_numeric_delta",
    "validate_derived_inputs",
]
