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
    if not _source_matches_candidate(source, candidate):
        raise ValueError("commerce evidence source does not match candidate identity")
    if not fact.source_ref.startswith(f"{source}#"):
        raise ValueError("commerce fact source does not match candidate identity")
    return CandidateEvidence(
        evidence_id=f"commerce-{candidate.product_id}-{candidate.variant_id}-{field}",
        source_kind=EvidenceSourceKind.COMMERCE,
        candidate=candidate,
        field=field,
        fact=fact,
        source_ref=source,
        observed_at=observed_at,
    )


def _commerce_source(candidate: CandidateIdentity) -> str:
    return (
        f"fixture://{candidate.store_id}/products/{candidate.product_id}"
        f"/variants/{candidate.variant_id}"
    )


def _source_matches_candidate(source: str, candidate: CandidateIdentity) -> bool:
    expected = _commerce_source(candidate)
    return source in {expected, f"{expected}/commerce"}


__all__ = ["build_commerce_evidence"]
