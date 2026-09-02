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
]
