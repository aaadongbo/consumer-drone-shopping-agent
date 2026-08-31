"""S02-T03 integration tests across constraints and catalog eligibility."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    DeterministicCatalogFixture,
    EligibilityRejectionCode,
    evaluate_store_eligibility,
    evaluate_variant_eligibility,
)
from backend.catalog.fixture import ISOLATION_STORE_ID, PRIMARY_STORE_ID
from backend.common import SCHEMA_VERSION, ConversationRef, PageContext, TurnRequest
from backend.conversation import normalize_constraint_patches, parse_constraint_patches

pytestmark = pytest.mark.integration

OBSERVED_AT = datetime(2026, 8, 31, 10, 30, tzinfo=UTC)


def turn(text: str, *, store_id: str = PRIMARY_STORE_ID) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=store_id,
        conversation=ConversationRef(
            conversation_id="conv-s02-t03",
            message_id="msg-s02-t03",
        ),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )


def load(store_id: str):
    return DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=store_id
    )


def constraints_from(text: str):
    return normalize_constraint_patches(parse_constraint_patches(turn(text)))


def test_budget_weight_and_battery_constraints_leave_only_lite_eligible() -> None:
    snapshot = load(PRIMARY_STORE_ID)
    constraints = constraints_from("预算5000元以内，250g以下，至少1块电池，适合旅行")

    results = evaluate_store_eligibility(snapshot=snapshot, constraints=constraints)

    eligible = [result.variant_id for result in results if result.eligible]
    assert eligible == ["travel-lite"]
    rejected = {result.variant_id: result for result in results if not result.eligible}
    assert rejected["travel-pack"].rejection_reasons[0].code is (
        EligibilityRejectionCode.VARIANT_UNAVAILABLE
    )
    assert {reason.code for reason in rejected["cinema-pro"].rejection_reasons} == {
        EligibilityRejectionCode.HARD_CONSTRAINT_NOT_SATISFIED,
    }
    assert EligibilityRejectionCode.HARD_FIELD_UNKNOWN in {
        reason.code for reason in rejected["survey-base"].rejection_reasons
    }


def test_evaluations_preserve_scope_and_current_observed_at() -> None:
    snapshot = load(PRIMARY_STORE_ID)
    constraints = constraints_from("预算5000元以内，至少1块电池")

    results = evaluate_store_eligibility(snapshot=snapshot, constraints=constraints)

    for result in results:
        assert result.store_id == PRIMARY_STORE_ID
        assert result.observed_at == OBSERVED_AT
        actual_observations = {
            item.actual.observed_at
            for item in result.evaluated_constraints
            if item.actual
        }
        assert actual_observations <= {
            OBSERVED_AT,
            None,
        }
        assert result.to_wire()["schema_version"] == SCHEMA_VERSION


def test_overlapping_ids_are_evaluated_only_within_their_store() -> None:
    primary = load(PRIMARY_STORE_ID)
    isolated = load(ISOLATION_STORE_ID)
    constraints = normalize_constraint_patches(
        parse_constraint_patches(
            turn("预算2500元以内，250g以下", store_id=ISOLATION_STORE_ID)
        )
    )

    isolated_results = evaluate_store_eligibility(
        snapshot=isolated,
        constraints=constraints,
    )
    primary_variant = next(
        variant
        for variant in primary.variants
        if variant.product_id == "drone-travel" and variant.variant_id == "travel-lite"
    )

    assert isolated_results[0].store_id == ISOLATION_STORE_ID
    assert isolated_results[0].variant_id == "travel-lite"
    assert isolated_results[0].eligible is False
    assert isolated_results[0].evaluated_constraints[0].actual is not None
    assert isolated_results[0].evaluated_constraints[0].actual.value == 1999
    with pytest.raises(ValueError, match="identities must match exactly"):
        evaluate_variant_eligibility(
            variant=primary_variant,
            commerce=isolated.commerce[0],
            constraints=constraints,
        )
