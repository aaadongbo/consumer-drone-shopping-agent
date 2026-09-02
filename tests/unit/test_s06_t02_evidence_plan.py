"""Unit coverage for per-product evidence planning."""

import pytest

from backend.agent import (
    EvidenceObjective,
    PerProductEvidenceBudget,
    RecommendationActionPlan,
    build_retrieval_requests,
)
from backend.evidence import CandidateIdentity

pytestmark = pytest.mark.unit


def _candidate(product_id: str, variant_id: str) -> CandidateIdentity:
    return CandidateIdentity(
        store_id="store-s02-alpha", product_id=product_id, variant_id=variant_id
    )


def _plan() -> tuple[RecommendationActionPlan, tuple[CandidateIdentity, ...]]:
    candidates = (
        _candidate("drone-travel", "travel-pack"),
        _candidate("drone-cinema", "cinema-pro"),
    )
    plan = RecommendationActionPlan(
        candidate_set=candidates,
        evidence_objectives=tuple(
            EvidenceObjective(
                candidate=candidate,
                field="package_list",
                question="What is included?",
            )
            for candidate in candidates
        ),
        per_product_budgets=tuple(
            PerProductEvidenceBudget(candidate=candidate) for candidate in candidates
        ),
    )
    return plan, candidates


def test_plan_requires_distinct_products_and_exact_budget_coverage() -> None:
    plan, candidates = _plan()
    assert len(plan.candidate_set) == 2
    assert {budget.candidate for budget in plan.per_product_budgets} == set(candidates)

    with pytest.raises(ValueError, match="distinct Products"):
        RecommendationActionPlan(
            candidate_set=(candidates[0], _candidate("drone-travel", "travel-lite")),
            evidence_objectives=(
                EvidenceObjective(
                    candidate=candidates[0], field="package_list", question="What?"
                ),
            ),
            per_product_budgets=(PerProductEvidenceBudget(candidate=candidates[0]),),
        )


def test_retrieval_requests_preserve_each_candidate_scope_and_budget() -> None:
    plan, candidates = _plan()
    requests = build_retrieval_requests(
        plan,
        {candidate: f"Question for {candidate.product_id}" for candidate in candidates},
    )
    assert [
        (item.turn_target.product_id, item.turn_target.variant_id) for item in requests
    ] == [("drone-travel", "travel-pack"), ("drone-cinema", "cinema-pro")]
    assert all(item.max_retrieval_tokens == 4000 for item in requests)


def test_action_plan_is_bounded_to_two_total_rounds() -> None:
    with pytest.raises(ValueError):
        plan, _ = _plan()
        RecommendationActionPlan(
            candidate_set=plan.candidate_set,
            evidence_objectives=plan.evidence_objectives,
            per_product_budgets=plan.per_product_budgets,
            max_action_rounds=3,
        )
