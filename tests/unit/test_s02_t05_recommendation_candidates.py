"""S02-T05 Product-grouped recommendation candidate tests."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    DeterministicCatalogFixture,
    evaluate_store_eligibility,
    rank_eligible_variants_by_soft_preferences,
)
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperator,
    ConstraintProvenance,
    NormalizedConstraint,
)
from backend.evidence import build_recommendation_candidates

pytestmark = pytest.mark.unit

OBSERVED_AT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def load():
    return DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=PRIMARY_STORE_ID
    )


def soft(
    field: ConstraintField,
    operator: ConstraintOperator,
    value: object,
) -> NormalizedConstraint:
    return NormalizedConstraint(
        source_turn_id="msg-s02-t05",
        field=field,
        operator=operator,
        value=value,
        unit=None,
        hardness=ConstraintHardness.SOFT,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def candidates_for(constraints):
    snapshot = load()
    eligibility = evaluate_store_eligibility(snapshot=snapshot, constraints=constraints)
    soft_scores = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=eligibility,
        constraints=constraints,
    )
    return build_recommendation_candidates(
        snapshot=snapshot,
        eligibility_results=eligibility,
        soft_scores=soft_scores,
    )


def test_candidates_are_grouped_to_at_most_three_distinct_products() -> None:
    result = candidates_for(
        [
            soft(ConstraintField.CAMERA_RESOLUTION, ConstraintOperator.EQ, "4K"),
            soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "travel"),
        ]
    )

    assert len(result.candidates) == 3
    assert len({candidate.product_id for candidate in result.candidates}) == 3
    assert [candidate.variant_id for candidate in result.candidates] == [
        "travel-lite",
        "survey-base",
        "cinema-pro",
    ]


def test_candidate_discloses_actual_variant_and_product_card_scope() -> None:
    result = candidates_for(
        [soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "cinema")]
    )
    candidate = result.candidates[0]

    assert candidate.product_id == "drone-cinema"
    assert candidate.variant_id == "cinema-pro"
    assert candidate.product_card.product_id == candidate.product_id
    assert candidate.product_card.variant_id == candidate.variant_id
    assert candidate.eligibility.variant_id == candidate.variant_id
    assert candidate.soft_score.variant_id == candidate.variant_id


def test_reasons_have_matching_claim_evidence_bindings() -> None:
    result = candidates_for(
        [soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "travel")]
    )
    candidate = result.candidates[0]
    evidence_by_id = {item.evidence_id: item for item in candidate.evidence}

    assert candidate.reasons
    for reason in candidate.reasons:
        assert reason.binding.claim_id == reason.claim.claim_id
        assert len(reason.binding.evidence_ids) == 1
        evidence = evidence_by_id[reason.binding.evidence_ids[0]]
        assert evidence.store_id == candidate.store_id
        assert evidence.product_id == candidate.product_id
        assert evidence.variant_id == candidate.variant_id
        assert evidence.fact == reason.claim.fact
        assert evidence.fact.source_ref == evidence.source


def test_same_product_appears_once_even_if_scores_repeat() -> None:
    snapshot = load()
    eligibility = evaluate_store_eligibility(snapshot=snapshot, constraints=[])
    scores = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=eligibility,
        constraints=[],
    )

    result = build_recommendation_candidates(
        snapshot=snapshot,
        eligibility_results=eligibility,
        soft_scores=(scores[0], scores[0], *scores[1:]),
    )

    assert len(result.candidates) == len(
        {item.product_id for item in result.candidates}
    )


def test_ineligible_variant_cannot_be_promoted_into_candidate() -> None:
    snapshot = load()
    eligibility = evaluate_store_eligibility(snapshot=snapshot, constraints=[])
    unavailable = next(item for item in eligibility if item.variant_id == "travel-pack")
    score = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=[next(item for item in eligibility if item.eligible)],
        constraints=[],
    )[0]
    bad_score = score.model_copy(
        update={
            "product_id": unavailable.product_id,
            "variant_id": unavailable.variant_id,
            "tie_break_key": (
                unavailable.product_id,
                unavailable.variant_id,
                unavailable.store_id,
            ),
        }
    )

    with pytest.raises(ValueError, match="eligible Variants"):
        build_recommendation_candidates(
            snapshot=snapshot,
            eligibility_results=eligibility,
            soft_scores=[bad_score],
        )
