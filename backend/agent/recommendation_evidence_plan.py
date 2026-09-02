"""Per-candidate evidence planning for Slice 6.

This module plans scoped retrieval work; it does not execute retrieval, refresh
commerce, rank candidates, or change the public response contract.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from backend.common.contracts import WireModel
from backend.evidence import CandidateIdentity
from backend.rag import RetrievalRequest

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class RecommendationEvidenceAction(StrEnum):
    """Typed action names available to the future recommendation loop."""

    RETRIEVE_PRODUCT_EVIDENCE = "RETRIEVE_PRODUCT_EVIDENCE"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    REFRESH_COMMERCE = "REFRESH_COMMERCE"
    COMPUTE_DERIVED_EVIDENCE = "COMPUTE_DERIVED_EVIDENCE"


class EvidenceObjective(WireModel):
    """One field objective owned by one exact recommendation candidate."""

    candidate: CandidateIdentity
    field: NonEmptyString
    question: NonEmptyString
    required: bool = True


class PerProductEvidenceBudget(WireModel):
    """Independent retrieval budget for one candidate."""

    candidate: CandidateIdentity
    max_retrieval_tokens: int = Field(default=4000, ge=1)
    max_tool_calls: int = Field(default=1, ge=1, le=2)


class RecommendationActionPlan(WireModel):
    """Bounded, replayable evidence plan for up to three candidates."""

    candidate_set: tuple[CandidateIdentity, ...] = Field(min_length=1, max_length=3)
    evidence_objectives: tuple[EvidenceObjective, ...] = Field(min_length=1)
    per_product_budgets: tuple[PerProductEvidenceBudget, ...] = Field(
        min_length=1, max_length=3
    )
    max_action_rounds: int = Field(default=2, ge=1, le=2)

    @model_validator(mode="after")
    def validate_plan(self) -> "RecommendationActionPlan":
        candidate_ids = [
            (item.store_id, item.product_id, item.variant_id)
            for item in self.candidate_set
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_set identities must be unique")
        product_ids = [(item.store_id, item.product_id) for item in self.candidate_set]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("candidate_set must contain distinct Products")

        candidate_set = set(candidate_ids)
        objective_ids = [
            (
                item.candidate.store_id,
                item.candidate.product_id,
                item.candidate.variant_id,
            )
            for item in self.evidence_objectives
        ]
        if any(identity not in candidate_set for identity in objective_ids):
            raise ValueError("evidence objective crossed candidate_set")

        budget_ids = [
            (
                item.candidate.store_id,
                item.candidate.product_id,
                item.candidate.variant_id,
            )
            for item in self.per_product_budgets
        ]
        if set(budget_ids) != candidate_set:
            raise ValueError("per_product_budgets must cover candidate_set exactly")
        if len(budget_ids) != len(set(budget_ids)):
            raise ValueError("per_product_budgets identities must be unique")
        return self


class RecommendationActionObservation(WireModel):
    """Summary-only observation for a future per-product action."""

    action: RecommendationEvidenceAction
    candidate: CandidateIdentity
    evidence_count: int = Field(ge=0)
    missing_fields: tuple[NonEmptyString, ...] = ()


class RecommendationActionRoundTrace(WireModel):
    """Internal trace for a recommendation evidence action round."""

    round_number: int = Field(ge=1, le=2)
    action: RecommendationEvidenceAction
    candidate: CandidateIdentity
    choice_reason: NonEmptyString
    observation: RecommendationActionObservation
    budget_tool_calls: int = Field(ge=0, le=2)
    budget_retrieval_tokens: int = Field(ge=0)
    final_stop_reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_observation_identity(self) -> "RecommendationActionRoundTrace":
        if self.observation.candidate != self.candidate:
            raise ValueError("action observation crossed candidate identity")
        if self.observation.action is not self.action:
            raise ValueError("action observation must match action")
        return self


def build_retrieval_requests(
    plan: RecommendationActionPlan,
    questions: Mapping[CandidateIdentity, str],
) -> tuple[RetrievalRequest, ...]:
    """Build typed, candidate-scoped retrieval requests without calling a retriever."""

    budgets = {item.candidate: item for item in plan.per_product_budgets}
    requests: list[RetrievalRequest] = []
    for objective in plan.evidence_objectives:
        question = questions.get(objective.candidate, objective.question)
        budget = budgets[objective.candidate]
        requests.append(
            RetrievalRequest(
                turn_target=objective.candidate.as_scope(),
                question=question,
                field_hint=objective.field,
                max_retrieval_tokens=budget.max_retrieval_tokens,
            )
        )
    return tuple(requests)


__all__ = [
    "EvidenceObjective",
    "PerProductEvidenceBudget",
    "RecommendationActionObservation",
    "RecommendationActionPlan",
    "RecommendationActionRoundTrace",
    "RecommendationEvidenceAction",
    "build_retrieval_requests",
]
