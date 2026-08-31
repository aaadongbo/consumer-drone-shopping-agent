"""S02-T04 deterministic SOFT preference baseline tests."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    DeterministicCatalogFixture,
    evaluate_store_eligibility,
    rank_eligible_variants_by_soft_preferences,
    score_soft_preferences,
)
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperator,
    ConstraintProvenance,
    NormalizedConstraint,
)

pytestmark = pytest.mark.unit

OBSERVED_AT = datetime(2026, 8, 31, 11, 0, tzinfo=UTC)


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
        source_turn_id="msg-s02-t04",
        field=field,
        operator=operator,
        value=value,
        unit=None,
        hardness=ConstraintHardness.SOFT,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def hard(
    field: ConstraintField,
    operator: ConstraintOperator,
    value: object,
    unit: str | None,
) -> NormalizedConstraint:
    return NormalizedConstraint(
        source_turn_id="msg-s02-t04",
        field=field,
        operator=operator,
        value=value,
        unit=unit,
        hardness=ConstraintHardness.HARD,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def eligible_results(constraints=()):
    snapshot = load()
    results = evaluate_store_eligibility(snapshot=snapshot, constraints=constraints)
    return snapshot, results


def test_soft_signals_match_product_and_variant_fields_transparently() -> None:
    snapshot, results = eligible_results()
    product = next(
        item for item in snapshot.products if item.product_id == "drone-cinema"
    )
    variant = next(
        item for item in snapshot.variants if item.variant_id == "cinema-pro"
    )
    eligibility = next(item for item in results if item.variant_id == "cinema-pro")

    score = score_soft_preferences(
        product=product,
        variant=variant,
        eligibility=eligibility,
        constraints=[
            soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "cinema"),
            soft(ConstraintField.CAMERA_RESOLUTION, ConstraintOperator.EQ, "5.1K"),
            soft(ConstraintField.OBSTACLE_SENSING, ConstraintOperator.PRESENT, True),
        ],
    )

    assert score is not None
    assert score.matched_soft_count == 3
    assert score.total_soft_count == 3
    assert [signal.matched for signal in score.signals] == [True, True, True]
    assert score.signals[0].actual is not None
    assert score.signals[0].actual.source_ref.endswith("#use_case")
    assert score.signals[2].actual is not None
    assert score.signals[2].actual.source_ref.endswith("#obstacle_sensing")


def test_rank_only_eligible_variants_and_never_promotes_hard_failures() -> None:
    snapshot, results = eligible_results(
        constraints=[
            hard(ConstraintField.TAKEOFF_WEIGHT, ConstraintOperator.LTE, 250, "g")
        ]
    )

    ranked = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=results,
        constraints=[
            soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "cinema"),
            soft(ConstraintField.CAMERA_RESOLUTION, ConstraintOperator.EQ, "5.1K"),
        ],
    )

    assert [item.variant_id for item in ranked] == ["travel-lite"]
    assert all(item.product_id != "drone-cinema" for item in ranked)


def test_soft_order_prefers_more_matches_then_stable_identity_tie_break() -> None:
    snapshot, results = eligible_results()

    ranked = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=results,
        constraints=[
            soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "travel"),
            soft(ConstraintField.CAMERA_RESOLUTION, ConstraintOperator.EQ, "4K"),
        ],
    )

    assert [
        (item.product_id, item.variant_id, item.matched_soft_count) for item in ranked
    ] == [
        ("drone-travel", "travel-lite", 2),
        ("drone-survey", "survey-base", 1),
        ("drone-cinema", "cinema-pro", 0),
    ]


def test_unknown_or_not_applicable_soft_fields_are_non_matches_not_failures() -> None:
    snapshot, results = eligible_results()

    ranked = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=results,
        constraints=[
            soft(ConstraintField.OBSTACLE_SENSING, ConstraintOperator.PRESENT, True)
        ],
    )

    lite = next(item for item in ranked if item.variant_id == "travel-lite")
    survey = next(item for item in ranked if item.variant_id == "survey-base")
    assert lite.matched_soft_count == 0
    assert lite.signals[0].reason == "Soft preference field is unknown."
    assert survey.matched_soft_count == 0
    assert survey.signals[0].reason == "Soft preference field is not applicable."


def test_ranking_is_deterministic_on_replay() -> None:
    snapshot, results = eligible_results()
    constraints = [
        soft(ConstraintField.USE_CASE, ConstraintOperator.EQ, "travel"),
        soft(ConstraintField.OBSTACLE_SENSING, ConstraintOperator.PRESENT, True),
    ]

    first = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=results,
        constraints=constraints,
    )
    second = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=results,
        constraints=constraints,
    )

    assert first == second
    one_match = [item.tie_break_key for item in first if item.matched_soft_count == 1]
    assert one_match == sorted(one_match)


def test_identity_mismatch_is_rejected_before_scoring() -> None:
    snapshot, results = eligible_results()
    product = next(
        item for item in snapshot.products if item.product_id == "drone-travel"
    )
    variant = next(
        item for item in snapshot.variants if item.product_id == "drone-cinema"
    )
    eligibility = next(item for item in results if item.product_id == "drone-cinema")

    with pytest.raises(ValueError, match="Product and Variant identities must match"):
        score_soft_preferences(
            product=product,
            variant=variant,
            eligibility=eligibility,
            constraints=[],
        )
