"""Evidence helpers for recommendation assembly and Product RAG gates."""

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
    "build_dynamic_comparison_facts",
    "build_static_comparison_facts",
    "build_recommendation_candidates",
    "read_dynamic_comparison_facts",
    "gate_retrieval_evidence",
    "reject_for_budget",
]
