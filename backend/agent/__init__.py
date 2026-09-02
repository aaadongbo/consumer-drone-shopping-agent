"""Bounded deterministic orchestration for recommendation and Product RAG."""

from backend.agent.product_rag import (
    ActionObservation,
    ActionPlan,
    ActionRoundTrace,
    ActionVerificationResult,
    BoundedProductRagLoop,
    BudgetConsumption,
    ProductRagBudget,
    ProductRagLoopResult,
    ProductRagRetriever,
    RagAction,
    RagStopReason,
)
from backend.agent.recommendation import (
    CatalogSnapshotProvider,
    Slice2RecommendationService,
    Slice2TraceSink,
)
from backend.agent.recommendation_evidence_plan import (
    EvidenceObjective,
    PerProductEvidenceBudget,
    RecommendationActionObservation,
    RecommendationActionPlan,
    RecommendationActionRoundTrace,
    RecommendationEvidenceAction,
    build_retrieval_requests,
)
from backend.agent.recommendation_explanation import (
    RecommendationExplanation,
    RecommendationExplanationResult,
    RecommendationFallback,
    RecommendationFallbackReason,
    SupportedReason,
    build_recommendation_explanation,
)

__all__ = [
    "ActionObservation",
    "ActionPlan",
    "ActionRoundTrace",
    "ActionVerificationResult",
    "BoundedProductRagLoop",
    "BudgetConsumption",
    "CatalogSnapshotProvider",
    "ProductRagBudget",
    "ProductRagLoopResult",
    "ProductRagRetriever",
    "RagAction",
    "RagStopReason",
    "Slice2RecommendationService",
    "Slice2TraceSink",
    "EvidenceObjective",
    "PerProductEvidenceBudget",
    "RecommendationActionObservation",
    "RecommendationActionPlan",
    "RecommendationActionRoundTrace",
    "RecommendationEvidenceAction",
    "build_retrieval_requests",
    "RecommendationExplanation",
    "RecommendationExplanationResult",
    "RecommendationFallback",
    "RecommendationFallbackReason",
    "SupportedReason",
    "build_recommendation_explanation",
]
