"""S02-T05 recommendation candidate contract tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.catalog import (
    DeterministicCatalogFixture,
    evaluate_store_eligibility,
    rank_eligible_variants_by_soft_preferences,
)
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.common import SCHEMA_VERSION
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperator,
    ConstraintProvenance,
    NormalizedConstraint,
)
from backend.evidence import RecommendationCandidateSet, build_recommendation_candidates

pytestmark = pytest.mark.contract

OBSERVED_AT = datetime(2026, 8, 31, 12, 30, tzinfo=UTC)


def soft(
    field: ConstraintField,
    operator: ConstraintOperator,
    value: object,
) -> NormalizedConstraint:
    return NormalizedConstraint(
        source_turn_id="msg-s02-t05-contract",
        field=field,
        operator=operator,
        value=value,
        unit=None,
        hardness=ConstraintHardness.SOFT,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def candidate_set() -> RecommendationCandidateSet:
    snapshot = DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=PRIMARY_STORE_ID
    )
    constraints = [soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "travel")]
    eligibility = evaluate_store_eligibility(snapshot=snapshot, constraints=constraints)
    scores = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=eligibility,
        constraints=constraints,
    )
    return build_recommendation_candidates(
        snapshot=snapshot,
        eligibility_results=eligibility,
        soft_scores=scores,
    )


def test_recommendation_candidate_set_round_trips_wire_json() -> None:
    original = candidate_set()

    restored = RecommendationCandidateSet.model_validate_json(original.to_wire_json())

    assert restored == original
    assert restored.schema_version == SCHEMA_VERSION
    assert restored.candidates[0].schema_version == SCHEMA_VERSION


def test_candidate_contract_forbids_unknown_extra_fields() -> None:
    wire = candidate_set().to_wire()
    wire["future_field"] = True

    with pytest.raises(ValidationError):
        RecommendationCandidateSet.model_validate(wire)


def test_candidate_contract_rejects_duplicate_product_groups() -> None:
    original = candidate_set()
    first = original.candidates[0].to_wire()

    with pytest.raises(ValidationError, match="distinct Products"):
        RecommendationCandidateSet.model_validate(
            {
                "schema_version": SCHEMA_VERSION,
                "store_id": original.store_id,
                "candidates": [first, first],
            }
        )


def test_candidate_contract_rejects_product_card_scope_mismatch() -> None:
    original = candidate_set()
    wire = original.to_wire()
    wire["candidates"][0]["product_card"]["variant_id"] = "other-variant"

    with pytest.raises(ValidationError, match="Product card"):
        RecommendationCandidateSet.model_validate(wire)


def test_candidate_contract_rejects_missing_bound_evidence() -> None:
    original = candidate_set()
    wire = original.to_wire()
    wire["candidates"][0]["reasons"][0]["binding"]["evidence_ids"] = ["missing"]

    with pytest.raises(ValidationError, match="missing evidence"):
        RecommendationCandidateSet.model_validate(wire)


def test_candidate_contract_keeps_variant_identity_without_envelope_change() -> None:
    wire = candidate_set().to_wire()
    candidate = wire["candidates"][0]

    assert candidate["store_id"] == PRIMARY_STORE_ID
    assert candidate["variant_id"]
    assert candidate["product_card"]["variant_id"] == candidate["variant_id"]
    assert "answer_envelope" not in wire
    assert "outcome" not in wire
