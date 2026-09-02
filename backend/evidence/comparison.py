"""S04-T03 per-member comparison facts and evidence bindings."""

from collections.abc import Iterable
from typing import Literal

from pydantic import model_validator

from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import AttributeStatus, AttributeValue, ObjectScope
from backend.common.contracts import SCHEMA_VERSION, WireModel
from backend.conversation import ComparisonScopeStatus, ComparisonSet

type SchemaVersion = Literal["1.0"]


class ComparisonEvidenceBinding(WireModel):
    comparison_fact_id: str
    member_id: str
    evidence_id: str
    scope: ObjectScope
    source_class: Literal["CATALOG"]
    source_locator: str
    scope_verdict: Literal["MATCHED"] = "MATCHED"

    @model_validator(mode="after")
    def validate_binding_scope(self) -> "ComparisonEvidenceBinding":
        if self.scope.variant_id is None:
            raise ValueError("Comparison evidence must bind to a concrete Variant")
        return self


class ComparisonFact(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    comparison_fact_id: str
    member_id: str
    field_key: str
    fact: AttributeValue
    state: AttributeStatus
    source_class: Literal["CATALOG"]
    catalog_revision: str
    binding: ComparisonEvidenceBinding

    @model_validator(mode="after")
    def validate_fact_binding(self) -> "ComparisonFact":
        if self.state != self.fact.status:
            raise ValueError("ComparisonFact state must match AttributeValue status")
        if self.binding.comparison_fact_id != self.comparison_fact_id:
            raise ValueError("Evidence binding must reference its comparison fact")
        if self.binding.member_id != self.member_id:
            raise ValueError("Evidence binding must match the fact member")
        if self.binding.source_locator != self.fact.source_ref:
            raise ValueError("Evidence binding locator must match the fact source")
        return self


class ComparisonFactSet(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    correlation_id: str
    facts: tuple[ComparisonFact, ...]

    @model_validator(mode="after")
    def validate_unique_fact_ids(self) -> "ComparisonFactSet":
        fact_ids = [fact.comparison_fact_id for fact in self.facts]
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("ComparisonFact IDs must be unique")
        member_fields = [(fact.member_id, fact.field_key) for fact in self.facts]
        if len(set(member_fields)) != len(member_fields):
            raise ValueError("ComparisonFact fields must be unique per member")
        return self


def build_static_comparison_facts(
    *,
    comparison_set: ComparisonSet,
    snapshot: CatalogFixtureSnapshot,
    field_keys: Iterable[str],
) -> ComparisonFactSet:
    """Build static catalog facts for each member without dynamic commerce reads."""
    if comparison_set.scope_status is not ComparisonScopeStatus.READY:
        raise ValueError("Static comparison facts require a READY comparison set")

    requested_fields = tuple(field_keys)
    if any(
        not isinstance(field, str) or not field.strip() for field in requested_fields
    ):
        raise ValueError("Comparison fact field keys must be non-empty")
    if len(set(requested_fields)) != len(requested_fields):
        raise ValueError("Comparison fact field keys must be unique")

    products = {product.product_id: product for product in snapshot.products}
    variants = {
        (variant.product_id, variant.variant_id): variant
        for variant in snapshot.variants
    }
    facts: list[ComparisonFact] = []
    for member in comparison_set.members:
        variant_id = member.scope.variant_id
        if member.scope.store_id != snapshot.store_id or variant_id is None:
            raise ValueError("Comparison member crossed catalog snapshot scope")
        product = products.get(member.scope.product_id)
        variant = variants.get((member.scope.product_id, variant_id))
        if product is None or variant is None:
            raise ValueError("Comparison member is missing catalog identity")
        if (
            product.store_id != member.scope.store_id
            or variant.store_id != member.scope.store_id
            or variant.product_id != product.product_id
        ):
            raise ValueError("Comparison member catalog identity is inconsistent")
        for field_key in requested_fields:
            fact = _catalog_fact(
                product.shared_attributes, variant.variant_attributes, field_key
            )
            if fact is None:
                continue
            fact_id = f"{comparison_set.correlation_id}-{member.member_id}-{field_key}"
            scope = ObjectScope(
                store_id=member.scope.store_id,
                product_id=member.scope.product_id,
                variant_id=variant_id,
            )
            binding = ComparisonEvidenceBinding(
                comparison_fact_id=fact_id,
                member_id=member.member_id,
                evidence_id=f"evidence-{fact_id}",
                scope=scope,
                source_class="CATALOG",
                source_locator=fact.source_ref,
            )
            facts.append(
                ComparisonFact(
                    comparison_fact_id=fact_id,
                    member_id=member.member_id,
                    field_key=field_key,
                    fact=fact,
                    state=fact.status,
                    source_class="CATALOG",
                    catalog_revision=member.catalog_revision,
                    binding=binding,
                )
            )
    return ComparisonFactSet(
        correlation_id=comparison_set.correlation_id,
        facts=tuple(facts),
    )


def _catalog_fact(
    product_attributes: dict[str, AttributeValue],
    variant_attributes: dict[str, AttributeValue],
    field_key: str,
) -> AttributeValue | None:
    variant_fact = variant_attributes.get(field_key)
    if variant_fact is not None:
        return variant_fact
    return product_attributes.get(field_key)
