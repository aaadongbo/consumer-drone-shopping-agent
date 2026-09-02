"""S04 comparison facts and member-scoped evidence bindings."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, model_validator

from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import (
    AttributeStatus,
    AttributeValue,
    ObjectScope,
    ToolResult,
    ToolStatus,
)
from backend.common.contracts import SCHEMA_VERSION, WireModel
from backend.conversation import ComparisonScopeStatus, ComparisonSet
from backend.shopify.port import CommerceState, ShopifyReadPort

type SchemaVersion = Literal["1.0"]


class ComparisonFactState(StrEnum):
    """State used by comparison facts, including dynamic degradation."""

    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ComparisonFreshnessVerdict(StrEnum):
    """Freshness outcome for one member-scoped commerce read."""

    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class ComparisonDegradationReason(StrEnum):
    """Fail-closed reason for a dynamic fact without a usable value."""

    READ_ERROR = "READ_ERROR"
    PARTIAL_RESULT = "PARTIAL_RESULT"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    STALE_RESULT = "STALE_RESULT"
    INVALID_OBSERVATION = "INVALID_OBSERVATION"
    MISSING_FIELD = "MISSING_FIELD"
    FACT_NOT_KNOWN = "FACT_NOT_KNOWN"


class ComparisonEvidenceBinding(WireModel):
    comparison_fact_id: str
    member_id: str
    evidence_id: str
    scope: ObjectScope
    source_class: Literal["CATALOG", "SHOPIFY_COMMERCE"]
    source_locator: str
    scope_verdict: Literal["MATCHED", "UNAVAILABLE"] = "MATCHED"

    @model_validator(mode="after")
    def validate_binding_scope(self) -> ComparisonEvidenceBinding:
        if self.scope.variant_id is None:
            raise ValueError("Comparison evidence must bind to a concrete Variant")
        return self


class ComparisonFact(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    comparison_fact_id: str
    member_id: str
    field_key: str
    fact: AttributeValue
    state: AttributeStatus | ComparisonFactState
    source_class: Literal["CATALOG", "SHOPIFY_COMMERCE"]
    catalog_revision: str
    observed_at: AwareDatetime | None = None
    freshness: ComparisonFreshness | None = None
    degradation_reason: ComparisonDegradationReason | None = None
    binding: ComparisonEvidenceBinding

    @model_validator(mode="after")
    def validate_fact_binding(self) -> ComparisonFact:
        if self.binding.comparison_fact_id != self.comparison_fact_id:
            raise ValueError("Evidence binding must reference its comparison fact")
        if self.binding.member_id != self.member_id:
            raise ValueError("Evidence binding must match the fact member")
        if self.binding.source_locator != self.fact.source_ref:
            raise ValueError("Evidence binding locator must match the fact source")
        if self.binding.source_class != self.source_class:
            raise ValueError("Evidence binding source must match the fact source")

        if self.source_class == "CATALOG":
            if self.state != self.fact.status:
                raise ValueError(
                    "ComparisonFact state must match AttributeValue status"
                )
            if not self.catalog_revision:
                raise ValueError("Catalog facts require a catalog revision")
            if self.observed_at is not None or self.freshness is not None:
                raise ValueError("Catalog facts must omit dynamic freshness")
            if self.degradation_reason is not None:
                raise ValueError("Catalog facts cannot carry degradation")
            if self.binding.scope_verdict != "MATCHED":
                raise ValueError("Catalog evidence scope must be MATCHED")
            return self

        if self.observed_at is None or self.freshness is None:
            raise ValueError("Dynamic facts require observation and freshness")
        if self.state == AttributeStatus.KNOWN:
            if self.fact.status is not AttributeStatus.KNOWN:
                raise ValueError("KNOWN dynamic facts require a known AttributeValue")
            if self.freshness.verdict is not ComparisonFreshnessVerdict.FRESH:
                raise ValueError("KNOWN dynamic facts require FRESH freshness")
            if self.degradation_reason is not None:
                raise ValueError("KNOWN dynamic facts cannot carry degradation")
            if self.binding.scope_verdict != "MATCHED":
                raise ValueError("Known commerce evidence scope must be MATCHED")
        elif self.state == ComparisonFactState.UNAVAILABLE:
            if self.fact.status is not AttributeStatus.UNKNOWN:
                raise ValueError("Unavailable dynamic facts must omit a value")
            if self.freshness.verdict is ComparisonFreshnessVerdict.FRESH:
                raise ValueError("Unavailable dynamic facts cannot be FRESH")
            if self.degradation_reason is None:
                raise ValueError("Unavailable dynamic facts require degradation")
            if self.binding.scope_verdict != "UNAVAILABLE":
                raise ValueError(
                    "Unavailable commerce evidence scope must be UNAVAILABLE"
                )
        else:
            raise ValueError("Dynamic facts must be KNOWN or UNAVAILABLE")
        return self


class ComparisonFreshness(WireModel):
    """Member-scoped freshness result for a dynamic comparison fact."""

    verdict: ComparisonFreshnessVerdict
    observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_observation_shape(self) -> ComparisonFreshness:
        if (
            self.verdict
            in {
                ComparisonFreshnessVerdict.FRESH,
                ComparisonFreshnessVerdict.STALE,
            }
            and self.observed_at is None
        ):
            raise ValueError("Fresh or stale results require observed_at")
        return self


class ComparisonFactSet(WireModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    correlation_id: str
    facts: tuple[ComparisonFact, ...]

    @model_validator(mode="after")
    def validate_unique_fact_ids(self) -> ComparisonFactSet:
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
    _require_ready_comparison_set(comparison_set, label="Static")

    requested_fields = _validate_field_keys(field_keys)

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


_DEFAULT_DYNAMIC_FIELDS = ("price", "inventory", "availability")


def build_dynamic_comparison_facts(
    *,
    comparison_set: ComparisonSet,
    shopify: ShopifyReadPort,
    now: datetime,
    freshness_window: timedelta = timedelta(minutes=5),
    field_keys: Iterable[str] = _DEFAULT_DYNAMIC_FIELDS,
) -> ComparisonFactSet:
    """Read current commerce facts with member identity and freshness guards."""
    _require_ready_comparison_set(comparison_set, label="Dynamic")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Dynamic comparison freshness clock must be timezone-aware")
    if freshness_window <= timedelta(0):
        raise ValueError("Dynamic comparison freshness window must be positive")

    requested_fields = _validate_field_keys(field_keys)
    facts: list[ComparisonFact] = []
    for member in comparison_set.members:
        if member.scope.variant_id is None:
            raise ValueError("Dynamic comparison members require a concrete Variant")
        expected_source = _commerce_source(member.scope)
        try:
            result = shopify.refresh_commerce_state(
                store_id=member.scope.store_id,
                product_id=member.scope.product_id,
                variant_id=member.scope.variant_id,
            )
        except Exception:
            facts.extend(
                _unavailable_dynamic_facts(
                    member=member,
                    field_keys=requested_fields,
                    source=expected_source,
                    observed_at=now,
                    freshness=ComparisonFreshness(
                        verdict=ComparisonFreshnessVerdict.UNAVAILABLE
                    ),
                    reason=ComparisonDegradationReason.READ_ERROR,
                )
            )
            continue

        result_observed_at = _aware_datetime(result.observed_at)
        freshness_verdict = _freshness_verdict(
            result_observed_at, now=now, freshness_window=freshness_window
        )
        freshness = ComparisonFreshness(
            verdict=freshness_verdict,
            observed_at=result_observed_at,
        )
        source = result.source or expected_source
        if not _source_matches_scope(source, member.scope):
            facts.extend(
                _unavailable_dynamic_facts(
                    member=member,
                    field_keys=requested_fields,
                    source=expected_source,
                    observed_at=result_observed_at or now,
                    freshness=ComparisonFreshness(
                        verdict=ComparisonFreshnessVerdict.UNAVAILABLE,
                        observed_at=result_observed_at,
                    ),
                    reason=ComparisonDegradationReason.IDENTITY_MISMATCH,
                )
            )
            continue

        if result_observed_at is None:
            reason = ComparisonDegradationReason.INVALID_OBSERVATION
        elif freshness_verdict is ComparisonFreshnessVerdict.STALE:
            reason = ComparisonDegradationReason.STALE_RESULT
        elif result.status is ToolStatus.ERROR or result.data is None:
            reason = ComparisonDegradationReason.READ_ERROR
        else:
            reason = None

        if reason is not None:
            facts.extend(
                _unavailable_dynamic_facts(
                    member=member,
                    field_keys=requested_fields,
                    source=source,
                    observed_at=result_observed_at or now,
                    freshness=freshness.model_copy(
                        update={
                            "verdict": (
                                ComparisonFreshnessVerdict.UNAVAILABLE
                                if reason
                                in {
                                    ComparisonDegradationReason.INVALID_OBSERVATION,
                                    ComparisonDegradationReason.READ_ERROR,
                                }
                                else freshness.verdict
                            )
                        }
                    ),
                    reason=reason,
                )
            )
            continue

        facts.extend(
            _dynamic_facts_from_result(
                member=member,
                result=result,
                field_keys=requested_fields,
                freshness=freshness,
            )
        )

    return ComparisonFactSet(
        correlation_id=comparison_set.correlation_id,
        facts=tuple(facts),
    )


read_dynamic_comparison_facts = build_dynamic_comparison_facts


def _require_ready_comparison_set(comparison_set: ComparisonSet, *, label: str) -> None:
    if comparison_set.scope_status is not ComparisonScopeStatus.READY:
        raise ValueError(f"{label} comparison facts require a READY comparison set")
    product_ids = {member.scope.product_id for member in comparison_set.members}
    if len(product_ids) != 1:
        raise ValueError(f"{label} comparison facts require same-Product members")


def _validate_field_keys(field_keys: Iterable[str]) -> tuple[str, ...]:
    fields = tuple(field_keys)
    if any(not isinstance(field, str) or not field.strip() for field in fields):
        raise ValueError("Comparison fact field keys must be non-empty")
    if len(set(fields)) != len(fields):
        raise ValueError("Comparison fact field keys must be unique")
    return fields


def _aware_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value


def _freshness_verdict(
    observed_at: datetime | None,
    *,
    now: datetime,
    freshness_window: timedelta,
) -> ComparisonFreshnessVerdict:
    if observed_at is None:
        return ComparisonFreshnessVerdict.UNAVAILABLE
    age = now - observed_at
    if age < timedelta(0) or age > freshness_window:
        return ComparisonFreshnessVerdict.STALE
    return ComparisonFreshnessVerdict.FRESH


def _commerce_source(scope: ObjectScope) -> str:
    if scope.variant_id is None:
        raise ValueError("Commerce source requires a concrete Variant")
    return (
        f"fixture://{scope.store_id}/products/{scope.product_id}"
        f"/variants/{scope.variant_id}"
    )


def _source_matches_scope(source: str, scope: ObjectScope) -> bool:
    try:
        expected = _commerce_source(scope)
    except ValueError:
        return False
    return source.split("#", 1)[0].rstrip("/") == expected


def _dynamic_facts_from_result(
    *,
    member,
    result: ToolResult[CommerceState],
    field_keys: tuple[str, ...],
    freshness: ComparisonFreshness,
) -> list[ComparisonFact]:
    assert result.data is not None
    facts: list[ComparisonFact] = []
    for field_key in field_keys:
        fact = result.data.get(field_key)
        missing = field_key in result.missing_fields or fact is None
        if missing:
            facts.extend(
                _unavailable_dynamic_facts(
                    member=member,
                    field_keys=(field_key,),
                    source=result.source,
                    observed_at=result.observed_at,
                    freshness=ComparisonFreshness(
                        verdict=ComparisonFreshnessVerdict.UNAVAILABLE,
                        observed_at=_aware_datetime(result.observed_at),
                    ),
                    reason=(
                        ComparisonDegradationReason.PARTIAL_RESULT
                        if result.status is ToolStatus.PARTIAL
                        else ComparisonDegradationReason.MISSING_FIELD
                    ),
                )
            )
            continue
        if (
            fact.status is not AttributeStatus.KNOWN
            or fact.observed_at != result.observed_at
            or not fact.source_ref.startswith(f"{result.source}#")
        ):
            facts.extend(
                _unavailable_dynamic_facts(
                    member=member,
                    field_keys=(field_key,),
                    source=result.source,
                    observed_at=result.observed_at,
                    freshness=ComparisonFreshness(
                        verdict=ComparisonFreshnessVerdict.UNAVAILABLE,
                        observed_at=_aware_datetime(result.observed_at),
                    ),
                    reason=ComparisonDegradationReason.IDENTITY_MISMATCH,
                )
            )
            continue
        facts.append(
            _dynamic_fact(
                member=member,
                field_key=field_key,
                fact=fact,
                freshness=freshness,
            )
        )
    return facts


def _dynamic_fact(*, member, field_key: str, fact: AttributeValue, freshness):
    fact_id = f"{member.member_id}-{field_key}"
    binding = ComparisonEvidenceBinding(
        comparison_fact_id=fact_id,
        member_id=member.member_id,
        evidence_id=f"evidence-{fact_id}",
        scope=member.scope,
        source_class="SHOPIFY_COMMERCE",
        source_locator=fact.source_ref,
    )
    return ComparisonFact(
        comparison_fact_id=fact_id,
        member_id=member.member_id,
        field_key=field_key,
        fact=fact,
        state=AttributeStatus.KNOWN,
        source_class="SHOPIFY_COMMERCE",
        catalog_revision=member.catalog_revision,
        observed_at=freshness.observed_at,
        freshness=freshness,
        binding=binding,
    )


def _unavailable_dynamic_facts(
    *,
    member,
    field_keys: tuple[str, ...],
    source: str,
    observed_at: datetime,
    freshness: ComparisonFreshness,
    reason: ComparisonDegradationReason,
) -> list[ComparisonFact]:
    facts: list[ComparisonFact] = []
    for field_key in field_keys:
        fact_id = f"{member.member_id}-{field_key}"
        source_locator = f"{source}#commerce.{field_key}"
        unavailable = AttributeValue(
            status=AttributeStatus.UNKNOWN,
            source_ref=source_locator,
        )
        binding = ComparisonEvidenceBinding(
            comparison_fact_id=fact_id,
            member_id=member.member_id,
            evidence_id=f"evidence-{fact_id}",
            scope=member.scope,
            source_class="SHOPIFY_COMMERCE",
            source_locator=source_locator,
            scope_verdict="UNAVAILABLE",
        )
        facts.append(
            ComparisonFact(
                comparison_fact_id=fact_id,
                member_id=member.member_id,
                field_key=field_key,
                fact=unavailable,
                state=ComparisonFactState.UNAVAILABLE,
                source_class="SHOPIFY_COMMERCE",
                catalog_revision=member.catalog_revision,
                observed_at=observed_at,
                freshness=freshness,
                degradation_reason=reason,
                binding=binding,
            )
        )
    return facts


def _catalog_fact(
    product_attributes: dict[str, AttributeValue],
    variant_attributes: dict[str, AttributeValue],
    field_key: str,
) -> AttributeValue | None:
    variant_fact = variant_attributes.get(field_key)
    if variant_fact is not None:
        return variant_fact
    return product_attributes.get(field_key)
