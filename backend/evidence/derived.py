"""Deterministic Derived Evidence helpers for Slice 6."""

from collections.abc import Iterable
from numbers import Real

from backend.common import AttributeStatus
from backend.evidence.recommendation_bundle import (
    CandidateEvidence,
    CandidateIdentity,
    DerivedEvidence,
)


def derive_budget_margin(
    *,
    candidate: CandidateIdentity,
    price_evidence: CandidateEvidence,
    budget: Real,
    derived_id: str = "derived-budget-margin",
) -> DerivedEvidence:
    """Compute ``budget - current price`` for one concrete candidate."""

    _ensure_numeric_fact(price_evidence, candidate, expected_field="price")
    assert price_evidence.fact is not None
    price = price_evidence.fact.value
    assert isinstance(price, int | float) and not isinstance(price, bool)
    if isinstance(budget, bool) or not isinstance(budget, Real):
        raise ValueError("budget must be numeric")
    return DerivedEvidence(
        evidence_id=derived_id,
        candidate=candidate,
        field="budget_margin",
        value=budget - price,
        unit=price_evidence.fact.unit,
        formula="budget - current_price",
        input_evidence_ids=(price_evidence.evidence_id,),
        observed_at=price_evidence.observed_at,
    )


def derive_numeric_delta(
    *,
    candidate: CandidateIdentity,
    first: CandidateEvidence,
    second: CandidateEvidence,
    derived_id: str,
    field: str | None = None,
) -> DerivedEvidence:
    """Compute ``first - second`` only for facts owned by the same candidate."""

    _ensure_numeric_fact(first, candidate)
    _ensure_numeric_fact(second, candidate)
    assert first.fact is not None and second.fact is not None
    first_value = first.fact.value
    second_value = second.fact.value
    assert isinstance(first_value, int | float) and not isinstance(first_value, bool)
    assert isinstance(second_value, int | float) and not isinstance(second_value, bool)
    return DerivedEvidence(
        evidence_id=derived_id,
        candidate=candidate,
        field=field or f"{first.field}_delta",
        value=first_value - second_value,
        unit=first.fact.unit or second.fact.unit,
        formula=f"{first.field} - {second.field}",
        input_evidence_ids=(first.evidence_id, second.evidence_id),
        observed_at=_latest_observed_at(first, second),
    )


def validate_derived_inputs(
    *, candidate: CandidateIdentity, inputs: Iterable[CandidateEvidence]
) -> tuple[str, ...]:
    """Return stable input IDs after enforcing one-candidate ownership."""

    items = tuple(inputs)
    if not items:
        raise ValueError("derived evidence requires at least one input")
    if any(item.candidate != candidate for item in items):
        raise ValueError("derived inputs crossed candidate identity")
    ids = tuple(item.evidence_id for item in items)
    if len(ids) != len(set(ids)):
        raise ValueError("derived inputs must have unique evidence IDs")
    return ids


def _ensure_numeric_fact(
    evidence: CandidateEvidence,
    candidate: CandidateIdentity,
    *,
    expected_field: str | None = None,
) -> None:
    if evidence.candidate != candidate:
        raise ValueError("evidence crossed candidate identity")
    if expected_field is not None and evidence.field != expected_field:
        raise ValueError(f"derived input must be {expected_field}")
    if evidence.fact is None or evidence.fact.status is not AttributeStatus.KNOWN:
        raise ValueError("derived input must be a KNOWN fact")
    if isinstance(evidence.fact.value, bool) or not isinstance(
        evidence.fact.value, int | float
    ):
        raise ValueError("derived input must be numeric")


def _latest_observed_at(first: CandidateEvidence, second: CandidateEvidence):
    timestamps = [item.observed_at for item in (first, second) if item.observed_at]
    return max(timestamps) if timestamps else None


__all__ = [
    "derive_budget_margin",
    "derive_numeric_delta",
    "validate_derived_inputs",
]
