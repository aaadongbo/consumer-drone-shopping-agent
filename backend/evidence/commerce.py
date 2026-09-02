"""Candidate-scoped commerce Evidence adapters for Slice 6."""

from datetime import datetime

from backend.catalog.fixture import CommerceState
from backend.common import AttributeValue, ToolResult, ToolStatus
from backend.evidence.recommendation_bundle import (
    CandidateEvidence,
    CandidateIdentity,
    EvidenceSourceKind,
)


def build_commerce_evidence(
    *, candidate: CandidateIdentity, result: ToolResult[CommerceState]
) -> tuple[CandidateEvidence, ...]:
    """Convert only the current ToolResult data into candidate-scoped evidence."""

    if result.status not in {ToolStatus.SUCCESS, ToolStatus.PARTIAL}:
        return ()
    if result.data is None:
        return ()
    return tuple(
        _evidence_for(
            candidate=candidate,
            field=field,
            fact=fact,
            source=result.source,
            observed_at=result.observed_at,
        )
        for field, fact in result.data.items()
    )


def _evidence_for(
    *,
    candidate: CandidateIdentity,
    field: str,
    fact: AttributeValue,
    source: str,
    observed_at: datetime,
) -> CandidateEvidence:
    if fact.observed_at is not None and fact.observed_at != observed_at:
        raise ValueError("commerce fact timestamp must match current ToolResult")
    return CandidateEvidence(
        evidence_id=f"commerce-{candidate.product_id}-{candidate.variant_id}-{field}",
        source_kind=EvidenceSourceKind.COMMERCE,
        candidate=candidate,
        field=field,
        fact=fact,
        source_ref=source,
        observed_at=observed_at,
    )


__all__ = ["build_commerce_evidence"]
