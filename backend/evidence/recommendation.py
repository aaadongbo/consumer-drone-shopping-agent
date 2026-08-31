"""Product-grouped recommendation contract for Slice 2."""

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, model_validator

from backend.catalog import (
    EligibilityResult,
    SoftPreferenceScore,
)
from backend.catalog.fixture import CatalogFixtureSnapshot, CommerceState
from backend.common import (
    AttributeStatus,
    AttributeValue,
    Claim,
    ClaimEvidenceBinding,
    Evidence,
    EvidenceType,
    ProductCard,
    ProductRecord,
    VariantRecord,
)
from backend.common.contracts import SCHEMA_VERSION, WireModel

type SchemaVersion = Literal["1.0"]

_MAX_PRODUCTS = 3


class RecommendationReason(WireModel):
    """One user-visible reason with explicit claim/evidence binding."""

    reason_id: str
    field: str
    claim: Claim
    binding: ClaimEvidenceBinding


class RecommendationCandidate(WireModel):
    """One actual Variant displayed under its owning Product."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    store_id: str
    product_id: str
    variant_id: str
    product_card: ProductCard
    variant_label: str
    eligibility: EligibilityResult
    soft_score: SoftPreferenceScore
    reasons: tuple[RecommendationReason, ...]
    evidence: tuple[Evidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_scope_and_bindings(self) -> "RecommendationCandidate":
        candidate_identity = (self.store_id, self.product_id, self.variant_id)
        if (
            self.product_card.store_id,
            self.product_card.product_id,
            self.product_card.variant_id,
        ) != candidate_identity:
            raise ValueError("Product card must match candidate identity")
        if (
            self.eligibility.store_id,
            self.eligibility.product_id,
            self.eligibility.variant_id,
        ) != candidate_identity:
            raise ValueError("Eligibility must match candidate identity")
        if (
            self.soft_score.store_id,
            self.soft_score.product_id,
            self.soft_score.variant_id,
        ) != candidate_identity:
            raise ValueError("Soft score must match candidate identity")

        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        for evidence in self.evidence:
            if (
                evidence.store_id,
                evidence.product_id,
                evidence.variant_id,
            ) != candidate_identity:
                raise ValueError("Evidence must match candidate identity")
        for reason in self.reasons:
            if reason.binding.claim_id != reason.claim.claim_id:
                raise ValueError("Claim binding must reference the reason claim")
            for evidence_id in reason.binding.evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    raise ValueError("Claim binding referenced missing evidence")
                if evidence.fact != reason.claim.fact:
                    raise ValueError("Claim fact must match bound evidence fact")
        return self


class RecommendationCandidateSet(WireModel):
    """The minimal Slice 2 candidate-list contract."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    store_id: str
    candidates: tuple[RecommendationCandidate, ...] = Field(max_length=_MAX_PRODUCTS)

    @model_validator(mode="after")
    def validate_product_grouping(self) -> "RecommendationCandidateSet":
        product_ids = [candidate.product_id for candidate in self.candidates]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Candidates must contain distinct Products")
        if any(candidate.store_id != self.store_id for candidate in self.candidates):
            raise ValueError("Candidates must stay within one store")
        return self


def build_recommendation_candidates(
    *,
    snapshot: CatalogFixtureSnapshot,
    eligibility_results: Iterable[EligibilityResult],
    soft_scores: Iterable[SoftPreferenceScore],
) -> RecommendationCandidateSet:
    """Build up to three Product-grouped candidates without final response text."""
    products = {product.product_id: product for product in snapshot.products}
    variants = {
        (variant.product_id, variant.variant_id): variant
        for variant in snapshot.variants
    }
    commerce = {
        (entry.product_id, entry.variant_id): entry.result.data
        for entry in snapshot.commerce
    }
    eligibility_by_identity = _unique_by_identity(
        eligibility_results,
        label="eligibility",
    )

    candidates: list[RecommendationCandidate] = []
    selected_products: set[str] = set()
    for score in soft_scores:
        if score.store_id != snapshot.store_id:
            raise ValueError("Soft score crossed the store boundary")
        score_identity = (score.product_id, score.variant_id)
        if score.product_id in selected_products:
            continue
        product = products[score.product_id]
        variant = variants[score_identity]
        eligibility = eligibility_by_identity[score_identity]
        if not eligibility.eligible:
            raise ValueError("Recommendation candidates require eligible Variants")
        candidate = _candidate_for(
            product=product,
            variant=variant,
            eligibility=eligibility,
            soft_score=score,
            commerce_state=commerce[(score.product_id, score.variant_id)],
        )
        candidates.append(candidate)
        selected_products.add(score.product_id)
        if len(candidates) == _MAX_PRODUCTS:
            break

    return RecommendationCandidateSet(
        store_id=snapshot.store_id,
        candidates=tuple(candidates),
    )


def _unique_by_identity(
    eligibility_results: Iterable[EligibilityResult],
    *,
    label: str,
) -> dict[tuple[str, str], EligibilityResult]:
    by_identity: dict[tuple[str, str], EligibilityResult] = {}
    for result in eligibility_results:
        identity = (result.product_id, result.variant_id)
        if identity in by_identity:
            raise ValueError(f"Duplicate {label} identity is not allowed")
        by_identity[identity] = result
    return by_identity


def _candidate_for(
    *,
    product: ProductRecord,
    variant: VariantRecord,
    eligibility: EligibilityResult,
    soft_score: SoftPreferenceScore,
    commerce_state: CommerceState | None,
) -> RecommendationCandidate:
    _ensure_identity(product, variant, eligibility, soft_score)
    if commerce_state is None:
        raise ValueError("Recommendation candidates require commerce facts")

    facts = _candidate_facts(product, variant, commerce_state)
    evidence = tuple(
        _evidence_for(
            product=product,
            variant=variant,
            field=field,
            fact=fact,
            index=index,
        )
        for index, (field, fact) in enumerate(facts, start=1)
    )
    reasons = tuple(
        _reason_for(field=field, fact=fact, evidence=evidence[index - 1], index=index)
        for index, (field, fact) in enumerate(facts, start=1)
    )
    return RecommendationCandidate(
        store_id=variant.store_id,
        product_id=variant.product_id,
        variant_id=variant.variant_id,
        product_card=ProductCard(
            store_id=product.store_id,
            product_id=product.product_id,
            variant_id=variant.variant_id,
            display_title=product.display_title,
        ),
        variant_label=variant.display_label,
        eligibility=eligibility,
        soft_score=soft_score,
        reasons=reasons,
        evidence=evidence,
    )


def _ensure_identity(
    product: ProductRecord,
    variant: VariantRecord,
    eligibility: EligibilityResult,
    soft_score: SoftPreferenceScore,
) -> None:
    product_variant_identity = (product.store_id, product.product_id)
    variant_owner = (variant.store_id, variant.product_id)
    if product_variant_identity != variant_owner:
        raise ValueError("Product and Variant identity mismatch")

    variant_identity = (variant.store_id, variant.product_id, variant.variant_id)
    eligibility_identity = (
        eligibility.store_id,
        eligibility.product_id,
        eligibility.variant_id,
    )
    score_identity = (soft_score.store_id, soft_score.product_id, soft_score.variant_id)
    if variant_identity != eligibility_identity or variant_identity != score_identity:
        raise ValueError("Candidate identity mismatch")


def _candidate_facts(
    _product: ProductRecord,
    variant: VariantRecord,
    commerce_state: CommerceState,
) -> tuple[tuple[str, AttributeValue], ...]:
    fields = (
        ("price", commerce_state["price"]),
        ("availability", commerce_state["availability"]),
        ("battery_count", variant.variant_attributes["battery_count"]),
        ("takeoff_weight", variant.variant_attributes["takeoff_weight"]),
    )
    return tuple(
        (field, fact) for field, fact in fields if fact.status is AttributeStatus.KNOWN
    )


def _evidence_for(
    *,
    product: ProductRecord,
    variant: VariantRecord,
    field: str,
    fact: AttributeValue,
    index: int,
) -> Evidence:
    return Evidence(
        evidence_id=f"candidate-{variant.product_id}-{variant.variant_id}-e{index}",
        type=EvidenceType.TOOL,
        store_id=variant.store_id,
        product_id=variant.product_id,
        variant_id=variant.variant_id,
        field_locator=f"products.{product.product_id}.variants.{variant.variant_id}.{field}",
        fact=fact,
        source=fact.source_ref,
        observed_at=fact.observed_at,
    )


def _reason_for(
    *,
    field: str,
    fact: AttributeValue,
    evidence: Evidence,
    index: int,
) -> RecommendationReason:
    claim = Claim(
        claim_id=f"candidate-{evidence.product_id}-{evidence.variant_id}-c{index}",
        field=field,
        fact=fact,
    )
    return RecommendationReason(
        reason_id=f"reason-{index}",
        field=field,
        claim=claim,
        binding=ClaimEvidenceBinding(
            claim_id=claim.claim_id,
            evidence_ids=[evidence.evidence_id],
        ),
    )
