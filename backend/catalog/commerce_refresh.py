"""Current commerce refresh and Variant-level HARD recheck adapter."""

from collections.abc import Iterable

from backend.catalog.eligibility import EligibilityResult, evaluate_variant_eligibility
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
) -> CommerceRefreshResult:
    """Refresh one explicit Variant and re-evaluate HARD constraints immediately."""

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


__all__ = ["CommerceRefreshResult", "refresh_and_recheck_candidate"]
