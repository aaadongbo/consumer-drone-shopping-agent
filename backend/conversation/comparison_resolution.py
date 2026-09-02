"""S04-T02 bounded comparison member validation."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import model_validator

from backend.common import SCHEMA_VERSION, ObjectScope
from backend.common.contracts import WireModel
from backend.conversation.comparison import (
    ComparisonMember,
    ComparisonScopeStatus,
    ComparisonSet,
    MemberProvenance,
    MemberSourceKind,
)
from backend.conversation.target_resolution import (
    ResolutionSource,
    TurnTarget,
    TurnTargetKind,
)

if TYPE_CHECKING:
    from backend.catalog.fixture import CatalogFixtureSnapshot

type SchemaVersion = Literal["1.0"]


class ComparisonFallbackReason(StrEnum):
    MEMBER_COUNT_OUT_OF_RANGE = "MEMBER_COUNT_OUT_OF_RANGE"
    MEMBER_DUPLICATE = "MEMBER_DUPLICATE"
    MEMBER_UNRESOLVED = "MEMBER_UNRESOLVED"
    PRODUCT_ONLY_REFERENCE = "PRODUCT_ONLY_REFERENCE"
    CROSS_STORE = "CROSS_STORE"
    CROSS_PRODUCT_DEFERRED = "CROSS_PRODUCT_DEFERRED"
    OWNERSHIP_MISMATCH = "OWNERSHIP_MISMATCH"


class ComparisonSetResolution(WireModel):
    """Result of validating an S03 COMPARISON_SET handoff for S04."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    correlation_id: str
    status: ComparisonScopeStatus
    comparison_set: ComparisonSet | None = None
    fallback_reason: ComparisonFallbackReason | None = None
    clarification_reason: str | None = None
    candidates: tuple[ObjectScope, ...] = ()

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> ComparisonSetResolution:
        if self.status is ComparisonScopeStatus.READY:
            if (
                self.comparison_set is None
                or self.fallback_reason is not None
                or self.clarification_reason is not None
                or self.candidates
            ):
                raise ValueError("READY resolution requires only comparison_set")
        elif self.fallback_reason is None or self.clarification_reason is None:
            raise ValueError("non-ready resolution requires fallback detail")
        return self


class ComparisonSetResolver:
    """Materialize a bounded Variant comparison set without reading facts."""

    def __init__(
        self, *, snapshot: CatalogFixtureSnapshot, catalog_revision: str
    ) -> None:
        self._snapshot = snapshot
        self._catalog_revision = catalog_revision
        self._products = {product.product_id: product for product in snapshot.products}
        self._variants = {
            (variant.product_id, variant.variant_id): variant
            for variant in snapshot.variants
        }
        self._variant_owners = {
            variant.variant_id: variant.product_id for variant in snapshot.variants
        }

    def materialize(
        self,
        *,
        target: TurnTarget,
        correlation_id: str,
        confirmed_context_revision: int = 0,
    ) -> ComparisonSetResolution:
        if target.kind is not TurnTargetKind.COMPARISON_SET:
            return self._fallback(
                correlation_id,
                ComparisonFallbackReason.MEMBER_UNRESOLVED,
                "target is not a COMPARISON_SET handoff",
            )

        members: list[ComparisonMember] = []
        for index, handoff_member in enumerate(target.comparison_members, start=1):
            fallback = self._validate_handoff_member(
                handoff_member.scope, correlation_id
            )
            if fallback is not None:
                return fallback
            if handoff_member.provenance not in {
                ResolutionSource.EXPLICIT,
                ResolutionSource.CONFIRMED_CONTEXT,
            }:
                return self._fallback(
                    correlation_id,
                    ComparisonFallbackReason.MEMBER_UNRESOLVED,
                    "comparison members require explicit or confirmed provenance",
                    candidates=(handoff_member.scope,),
                )

            variant = self._variants[
                (handoff_member.scope.product_id, handoff_member.scope.variant_id)
            ]
            product = self._products[variant.product_id]
            source_kind = MemberSourceKind(handoff_member.provenance.value)
            provenance = (
                MemberProvenance(
                    source_kind=source_kind,
                    original_reference=f"{variant.product_id}/{variant.variant_id}",
                    resolver_outcome="variant_handoff_validated",
                )
                if source_kind is MemberSourceKind.EXPLICIT
                else MemberProvenance(
                    source_kind=source_kind,
                    context_revision=confirmed_context_revision,
                    resolver_outcome="confirmed_context_variant_validated",
                )
            )
            members.append(
                ComparisonMember(
                    member_id=f"member-{index}",
                    scope=handoff_member.scope,
                    provenance=provenance,
                    resolution_reason="S03 comparison handoff member validated",
                    catalog_revision=self._catalog_revision,
                    display_name=f"{product.display_title} / {variant.display_label}",
                )
            )

        scopes = [member.scope for member in members]
        product_ids = {member.scope.product_id for member in members}
        comparison = ComparisonSet(
            correlation_id=correlation_id,
            store_id=self._snapshot.store_id,
            members=tuple(members),
            **(
                {}
                if len(product_ids) == 1
                else {
                    "scope_status": ComparisonScopeStatus.TYPED_DEFERRAL,
                    "fallback_reason": (
                        ComparisonFallbackReason.CROSS_PRODUCT_DEFERRED.value
                    ),
                    "clarification_reason": (
                        "Slice 4 only admits same-Product Variant comparison"
                    ),
                }
            ),
        )
        if len(product_ids) != 1:
            return ComparisonSetResolution(
                correlation_id=correlation_id,
                status=ComparisonScopeStatus.TYPED_DEFERRAL,
                comparison_set=comparison,
                fallback_reason=ComparisonFallbackReason.CROSS_PRODUCT_DEFERRED,
                clarification_reason=(
                    "Slice 4 only admits same-Product Variant comparison"
                ),
                candidates=tuple(scopes),
            )
        return ComparisonSetResolution(
            correlation_id=correlation_id,
            status=ComparisonScopeStatus.READY,
            comparison_set=comparison,
        )

    def _validate_handoff_member(
        self, scope: ObjectScope, correlation_id: str
    ) -> ComparisonSetResolution | None:
        if scope.store_id != self._snapshot.store_id:
            return self._fallback(
                correlation_id,
                ComparisonFallbackReason.CROSS_STORE,
                "comparison members must belong to the resolver store",
                candidates=(scope,),
            )
        if scope.variant_id is None:
            return self._fallback(
                correlation_id,
                ComparisonFallbackReason.PRODUCT_ONLY_REFERENCE,
                "comparison members must resolve to concrete Variants",
                candidates=(scope,),
            )
        if (scope.product_id, scope.variant_id) not in self._variants:
            if self._variant_owners.get(scope.variant_id) is not None:
                reason = ComparisonFallbackReason.OWNERSHIP_MISMATCH
                message = "Variant is not owned by the supplied Product"
            else:
                reason = ComparisonFallbackReason.MEMBER_UNRESOLVED
                message = "comparison member Variant is not in the catalog snapshot"
            return self._fallback(
                correlation_id,
                reason,
                message,
                candidates=(scope,),
            )
        return None

    @staticmethod
    def _fallback(
        correlation_id: str,
        reason: ComparisonFallbackReason,
        clarification_reason: str,
        *,
        candidates: tuple[ObjectScope, ...] = (),
    ) -> ComparisonSetResolution:
        return ComparisonSetResolution(
            correlation_id=correlation_id,
            status=ComparisonScopeStatus.NEEDS_CLARIFICATION,
            fallback_reason=reason,
            clarification_reason=clarification_reason,
            candidates=candidates,
        )
