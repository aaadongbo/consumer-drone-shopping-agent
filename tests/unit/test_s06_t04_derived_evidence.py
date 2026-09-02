"""Unit coverage for deterministic Derived Evidence."""

from datetime import UTC, datetime

import pytest

from backend.common import AttributeStatus, AttributeValue
from backend.evidence import (
    CandidateEvidence,
    CandidateIdentity,
    EvidenceSourceKind,
    derive_budget_margin,
    derive_numeric_delta,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _candidate(variant_id: str = "travel-pack") -> CandidateIdentity:
    return CandidateIdentity(
        store_id="store-drone-cn", product_id="drone-travel", variant_id=variant_id
    )


def _evidence(
    candidate: CandidateIdentity, evidence_id: str, field: str, value: object
) -> CandidateEvidence:
    return CandidateEvidence(
        evidence_id=evidence_id,
        source_kind=(
            EvidenceSourceKind.COMMERCE
            if field == "price"
            else EvidenceSourceKind.CATALOG
        ),
        candidate=candidate,
        field=field,
        fact=AttributeValue(
            status=AttributeStatus.KNOWN,
            value=value,
            source_ref=f"fixture://{field}",
            observed_at=_NOW,
        ),
        source_ref=f"fixture://{field}",
        observed_at=_NOW if field == "price" else None,
    )


def test_budget_margin_is_replayable_and_binds_current_price() -> None:
    candidate = _candidate()
    price = _evidence(candidate, "price", "price", 4999)
    derived = derive_budget_margin(
        candidate=candidate, price_evidence=price, budget=6000
    )

    assert derived.value == 1001
    assert derived.input_evidence_ids == ("price",)
    assert derived.formula == "budget - current_price"
    assert derived.observed_at == _NOW


def test_numeric_delta_requires_known_same_candidate_facts() -> None:
    candidate = _candidate()
    weight = _evidence(candidate, "weight-a", "takeoff_weight", 253)
    battery = _evidence(candidate, "battery-a", "battery_count", 3)
    delta = derive_numeric_delta(
        candidate=candidate,
        first=weight,
        second=battery,
        derived_id="weight-battery-delta",
        field="custom_delta",
    )
    assert delta.value == 250
    assert delta.input_evidence_ids == ("weight-a", "battery-a")

    with pytest.raises(ValueError, match="candidate identity"):
        derive_numeric_delta(
            candidate=candidate,
            first=weight,
            second=_evidence(_candidate("travel-lite"), "foreign", "battery_count", 1),
            derived_id="invalid",
        )


def test_budget_margin_rejects_unknown_or_non_numeric_price() -> None:
    candidate = _candidate()
    unknown = _evidence(candidate, "unknown", "price", 4999).model_copy(
        update={
            "fact": AttributeValue(
                status=AttributeStatus.UNKNOWN, source_ref="fixture://price"
            )
        }
    )
    with pytest.raises(ValueError, match="KNOWN"):
        derive_budget_margin(candidate=candidate, price_evidence=unknown, budget=6000)
