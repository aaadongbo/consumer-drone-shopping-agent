"""Fail-closed quality checks for static Product RAG evidence.

This module is deliberately internal.  It evaluates a retrieval result before
Slice 5's later answer flow can turn a document excerpt into a user-visible
claim; it does not create an ``AnswerEnvelope`` or read dynamic commerce data.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from backend.common import ObjectScope
from backend.rag.adapters import RetrievalEvidenceBundle, adapt_retrieval_result
from backend.rag.manifest import DocumentChunk, RagModel
from backend.rag.retrieval import RetrievalResult

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

_DYNAMIC_COMMERCE_FIELDS = frozenset({"price", "inventory", "availability"})


class EvidenceQualityVerdict(StrEnum):
    """Whether a proposed static claim is usable for an answer."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class RagFallbackReason(StrEnum):
    """Stable internal reasons for refusing a document-backed claim."""

    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    DYNAMIC_FACT_REQUIRED = "DYNAMIC_FACT_REQUIRED"
    STALE_VERSION = "STALE_VERSION"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class RagClaim(RagModel):
    """A proposed verbatim static claim and the chunk expected to support it."""

    claim_id: NonEmptyString
    scope: ObjectScope
    field: NonEmptyString
    text: NonEmptyString
    locator: NonEmptyString


class RagFallback(RagModel):
    """Internal fail-closed outcome; public fallback mapping belongs to T06."""

    claim_id: NonEmptyString
    reason: RagFallbackReason


class EvidenceQuality(RagModel):
    """Replayable quality verdict for one proposed claim."""

    claim_id: NonEmptyString
    verdict: EvidenceQualityVerdict
    scope_match: bool
    locator_present: bool
    version_match: bool
    claim_covered: bool
    conflict: bool
    evidence_locators: tuple[NonEmptyString, ...] = Field(default_factory=tuple)
    fallback: RagFallback | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "EvidenceQuality":
        if self.verdict is EvidenceQualityVerdict.ACCEPTED:
            if self.fallback is not None:
                raise ValueError("accepted evidence cannot carry a fallback")
            if not (
                self.scope_match
                and self.locator_present
                and self.version_match
                and self.claim_covered
                and not self.conflict
                and self.evidence_locators
            ):
                raise ValueError("accepted evidence requires every quality gate")
        elif self.fallback is None:
            raise ValueError("rejected evidence requires a fallback")
        return self


class EvidenceGateResult(RagModel):
    """The internal gate result consumed by later Slice 5 orchestration."""

    retrieval: RetrievalEvidenceBundle
    quality: tuple[EvidenceQuality, ...]

    @model_validator(mode="after")
    def validate_unique_claims(self) -> "EvidenceGateResult":
        claim_ids = [item.claim_id for item in self.quality]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("evidence quality must contain unique claim IDs")
        return self

    @property
    def accepted_claim_ids(self) -> tuple[str, ...]:
        return tuple(
            item.claim_id
            for item in self.quality
            if item.verdict is EvidenceQualityVerdict.ACCEPTED
        )

    @property
    def fallbacks(self) -> tuple[RagFallback, ...]:
        return tuple(
            item.fallback for item in self.quality if item.fallback is not None
        )


def gate_retrieval_evidence(
    result: RetrievalResult | RetrievalEvidenceBundle,
    *,
    claims: tuple[RagClaim, ...],
) -> EvidenceGateResult:
    """Accept only exact, current, target-scoped document support.

    ``RagClaim.text`` is intentionally an exact excerpt requirement at this
    stage.  It prevents an unverified paraphrase or model common knowledge from
    being promoted into a factual answer before T06 adds answer composition.
    """
    bundle = adapt_retrieval_result(result)
    return EvidenceGateResult(
        retrieval=bundle,
        quality=tuple(_evaluate_claim(bundle, claim) for claim in claims),
    )


def reject_for_budget(gate: EvidenceGateResult) -> EvidenceGateResult:
    """Downgrade otherwise supported claims when the turn budget is exhausted."""
    return EvidenceGateResult(
        retrieval=gate.retrieval,
        quality=tuple(
            EvidenceQuality(
                claim_id=item.claim_id,
                verdict=EvidenceQualityVerdict.REJECTED,
                scope_match=item.scope_match,
                locator_present=item.locator_present,
                version_match=item.version_match,
                claim_covered=item.claim_covered,
                conflict=item.conflict,
                evidence_locators=item.evidence_locators,
                fallback=RagFallback(
                    claim_id=item.claim_id,
                    reason=RagFallbackReason.BUDGET_EXHAUSTED,
                ),
            )
            if item.verdict is EvidenceQualityVerdict.ACCEPTED
            else item
            for item in gate.quality
        ),
    )


def _evaluate_claim(
    bundle: RetrievalEvidenceBundle, claim: RagClaim
) -> EvidenceQuality:
    if claim.field.casefold() in _DYNAMIC_COMMERCE_FIELDS:
        return _rejected(
            claim,
            reason=RagFallbackReason.DYNAMIC_FACT_REQUIRED,
            scope_match=claim.scope == bundle.request.turn_target,
        )

    if claim.scope != bundle.request.turn_target:
        return _rejected(claim, reason=RagFallbackReason.SCOPE_MISMATCH)

    matching_locator = tuple(
        chunk for chunk in bundle.evidence if chunk.locator.locator == claim.locator
    )
    if not matching_locator:
        return _rejected(claim, reason=RagFallbackReason.EVIDENCE_MISSING)

    if any(
        not _matches_target_scope(chunk, bundle.request.turn_target)
        for chunk in matching_locator
    ):
        return _rejected(
            claim,
            reason=RagFallbackReason.SCOPE_MISMATCH,
            locator_present=True,
            evidence_locators=_locators(matching_locator),
        )

    if any(not _has_current_version(chunk, bundle) for chunk in matching_locator):
        return _rejected(
            claim,
            reason=RagFallbackReason.STALE_VERSION,
            scope_match=True,
            locator_present=True,
            evidence_locators=_locators(matching_locator),
        )

    if len({chunk.text for chunk in matching_locator}) != 1:
        return _rejected(
            claim,
            reason=RagFallbackReason.CONFLICTING_EVIDENCE,
            scope_match=True,
            locator_present=True,
            version_match=True,
            conflict=True,
            evidence_locators=_locators(matching_locator),
        )

    covered = claim.text.casefold() in matching_locator[0].text.casefold()
    if not covered:
        return _rejected(
            claim,
            reason=RagFallbackReason.EVIDENCE_MISSING,
            scope_match=True,
            locator_present=True,
            version_match=True,
            evidence_locators=_locators(matching_locator),
        )

    return EvidenceQuality(
        claim_id=claim.claim_id,
        verdict=EvidenceQualityVerdict.ACCEPTED,
        scope_match=True,
        locator_present=True,
        version_match=True,
        claim_covered=True,
        conflict=False,
        evidence_locators=_locators(matching_locator),
    )


def _rejected(
    claim: RagClaim,
    *,
    reason: RagFallbackReason,
    scope_match: bool = False,
    locator_present: bool = False,
    version_match: bool = False,
    claim_covered: bool = False,
    conflict: bool = False,
    evidence_locators: tuple[str, ...] = (),
) -> EvidenceQuality:
    return EvidenceQuality(
        claim_id=claim.claim_id,
        verdict=EvidenceQualityVerdict.REJECTED,
        scope_match=scope_match,
        locator_present=locator_present,
        version_match=version_match,
        claim_covered=claim_covered,
        conflict=conflict,
        evidence_locators=evidence_locators,
        fallback=RagFallback(claim_id=claim.claim_id, reason=reason),
    )


def _matches_target_scope(chunk: DocumentChunk, target: ObjectScope) -> bool:
    if chunk.store_id != target.store_id or chunk.product_id != target.product_id:
        return False
    if target.variant_id is None:
        return chunk.variant_id is None
    return chunk.variant_id in (None, target.variant_id)


def _has_current_version(chunk: DocumentChunk, bundle: RetrievalEvidenceBundle) -> bool:
    source_version_bound = (
        chunk.locator.version == chunk.version
        and chunk.locator.source_id == chunk.source_id
    )
    if not source_version_bound:
        return False
    if "manifest_identity" in chunk.metadata:
        return chunk.metadata["manifest_identity"] == bundle.index_version
    return chunk.version == bundle.index_version


def _locators(chunks: tuple[DocumentChunk, ...]) -> tuple[str, ...]:
    return tuple(chunk.locator.locator for chunk in chunks)


__all__ = [
    "EvidenceGateResult",
    "EvidenceQuality",
    "EvidenceQualityVerdict",
    "RagClaim",
    "RagFallback",
    "RagFallbackReason",
    "gate_retrieval_evidence",
    "reject_for_budget",
]
