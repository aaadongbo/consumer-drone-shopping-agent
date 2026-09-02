"""Evidence helpers for recommendation assembly."""

from backend.evidence.comparison import (
    ComparisonEvidenceBinding,
    ComparisonFact,
    ComparisonFactSet,
    build_static_comparison_facts,
)
from backend.evidence.recommendation import (
    RecommendationCandidate,
    RecommendationCandidateSet,
    RecommendationReason,
    build_recommendation_candidates,
)

__all__ = [
    "ComparisonEvidenceBinding",
    "ComparisonFact",
    "ComparisonFactSet",
    "RecommendationCandidate",
    "RecommendationCandidateSet",
    "RecommendationReason",
    "build_static_comparison_facts",
    "build_recommendation_candidates",
]
