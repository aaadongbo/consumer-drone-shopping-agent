"""Current commerce refresh and Variant-level HARD recheck adapter."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from backend.catalog.eligibility import (
    EligibilityRejectionCode,
    EligibilityRejectionReason,
    EligibilityResult,
    evaluate_variant_eligibility,
)
from backend.catalog.fixture import VariantCommerceSnapshot
from backend.common import ToolResult, VariantRecord
from backend.common.contracts import WireModel
from backend.conversation import NormalizedConstraint
from backend.evidence import (
    CandidateEvidence,
    CandidateIdentity,
    build_commerce_evidence,
)
from backend.shopify import CommerceState, ShopifyReadPort


class CommerceRefreshResult(WireModel):
    """One current ToolResult plus the deterministic HARD recheck result."""

    candidate: CandidateIdentity
    result: ToolResult[CommerceState]
    eligibility: EligibilityResult
    evidence: tuple[CandidateEvidence, ...] = ()


def refresh_and_recheck_candidate(
    *,
    shopify: ShopifyReadPort,
    variant: VariantRecord,
    constraints: Iterable[NormalizedConstraint] = (),
    now: datetime | None = None,
    freshness_window: timedelta = timedelta(minutes=5),
) -> CommerceRefreshResult:
    """Refresh one explicit Variant and re-evaluate HARD constraints immediately."""

    if freshness_window <= timedelta(0):
        raise ValueError("commerce freshness window must be positive")
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("commerce freshness clock must be timezone-aware")

    candidate = CandidateIdentity(
        store_id=variant.store_id,
        product_id=variant.product_id,
        variant_id=variant.variant_id,
    )
    result = shopify.refresh_commerce_state(
        store_id=candidate.store_id,
        product_id=candidate.product_id,
        variant_id=candidate.variant_id,
    )
    if not _source_matches_candidate(result.source, candidate):
        return _rejected_refresh(
            candidate=candidate,
            result=result,
            variant=variant,
            constraints=constraints,
            message="Current commerce source does not match candidate identity.",
        )
    reference_time = now or result.observed_at
    age = reference_time - result.observed_at
    if age < timedelta(0) or age > freshness_window:
        return _rejected_refresh(
            candidate=candidate,
            result=result,
            variant=variant,
            constraints=constraints,
            message="Current commerce result is outside the freshness window.",
        )
    snapshot = VariantCommerceSnapshot(
        store_id=candidate.store_id,
        product_id=candidate.product_id,
        variant_id=candidate.variant_id,
        result=result,
    )
    eligibility = evaluate_variant_eligibility(
        variant=variant,
        commerce=snapshot,
        constraints=constraints,
    )
    return CommerceRefreshResult(
        candidate=candidate,
        result=result,
        eligibility=eligibility,
        evidence=build_commerce_evidence(candidate=candidate, result=result),
    )


def _rejected_refresh(
    *,
    candidate: CandidateIdentity,
    result: ToolResult[CommerceState],
    variant: VariantRecord,
    constraints: Iterable[NormalizedConstraint],
    message: str,
) -> CommerceRefreshResult:
    """Return an ineligible result without allowing invalid data into evidence."""

    snapshot = VariantCommerceSnapshot(
        store_id=candidate.store_id,
        product_id=candidate.product_id,
        variant_id=candidate.variant_id,
        result=result,
    )
    evaluated = evaluate_variant_eligibility(
        variant=variant,
        commerce=snapshot,
        constraints=constraints,
    )
    rejection = EligibilityRejectionReason(
        code=EligibilityRejectionCode.COMMERCE_RESULT_ERROR,
        field="commerce",
        message=message,
    )
    return CommerceRefreshResult(
        candidate=candidate,
        result=result,
        eligibility=evaluated.model_copy(
            update={
                "eligible": False,
                "rejection_reasons": (*evaluated.rejection_reasons, rejection),
            }
        ),
        evidence=(),
    )


def _commerce_source(candidate: CandidateIdentity) -> str:
    return (
        f"fixture://{candidate.store_id}/products/{candidate.product_id}"
        f"/variants/{candidate.variant_id}"
    )


def _source_matches_candidate(source: str, candidate: CandidateIdentity) -> bool:
    expected = _commerce_source(candidate)
    return source in {expected, f"{expected}/commerce"}


__all__ = ["CommerceRefreshResult", "refresh_and_recheck_candidate"]
