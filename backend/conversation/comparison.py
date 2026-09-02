"""Slice-local comparison identity contracts for Variant comparison."""

from enum import StrEnum
from typing import Literal

from pydantic import model_validator

from backend.common import SCHEMA_VERSION, ObjectScope
from backend.common.contracts import WireModel

type SchemaVersion = Literal["1.0"]


class MemberSourceKind(StrEnum):
    EXPLICIT = "EXPLICIT"
    CONFIRMED_CONTEXT = "CONFIRMED_CONTEXT"


class ComparisonScopeStatus(StrEnum):
    READY = "READY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    TYPED_DEFERRAL = "TYPED_DEFERRAL"
    FALLBACK = "FALLBACK"


class MemberProvenance(WireModel):
    """Auditable source for one comparison member."""

    source_kind: MemberSourceKind
    original_reference: str | None = None
    context_revision: int | None = None
    resolver_outcome: str

    @model_validator(mode="after")
    def validate_source_shape(self) -> "MemberProvenance":
        if self.source_kind is MemberSourceKind.EXPLICIT:
            if self.original_reference is None:
                raise ValueError("EXPLICIT provenance requires original_reference")
            if self.context_revision is not None:
                raise ValueError("EXPLICIT provenance must omit context_revision")
        else:
            if self.context_revision is None:
                raise ValueError(
                    "CONFIRMED_CONTEXT provenance requires context_revision"
                )
            if self.original_reference is not None:
                raise ValueError(
                    "CONFIRMED_CONTEXT provenance must omit original_reference"
                )
        return self


class ComparisonMember(WireModel):
    """One immutable Variant member in a comparison set."""

    member_id: str
    scope: ObjectScope
    provenance: MemberProvenance
    resolution_reason: str
    catalog_revision: str
    display_name: str

    @model_validator(mode="after")
    def validate_variant_identity(self) -> "ComparisonMember":
        if self.scope.variant_id is None:
            raise ValueError("comparison members require a concrete variant_id")
        return self


class ComparisonSet(WireModel):
    """Bounded, turn-local comparison set that never writes conversation state."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    correlation_id: str
    store_id: str
    members: tuple[ComparisonMember, ...]
    source_intent: Literal["COMPARISON_SET"] = "COMPARISON_SET"
    scope_status: ComparisonScopeStatus = ComparisonScopeStatus.READY
    clarification_reason: str | None = None
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def validate_comparison_set(self) -> "ComparisonSet":
        if not 2 <= len(self.members) <= 4:
            raise ValueError("ComparisonSet requires two to four members")

        member_ids = [member.member_id for member in self.members]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("ComparisonSet member_id values must be unique")

        scopes = [member.scope for member in self.members]
        if len(set(scopes)) != len(scopes):
            raise ValueError("ComparisonSet member scopes must be unique")

        if any(member.scope.store_id != self.store_id for member in self.members):
            raise ValueError("ComparisonSet members must match store_id")

        if self.scope_status is ComparisonScopeStatus.READY:
            if (
                self.clarification_reason is not None
                or self.fallback_reason is not None
            ):
                raise ValueError("READY ComparisonSet must omit fallback reasons")
        elif self.clarification_reason is None and self.fallback_reason is None:
            raise ValueError(
                "non-ready ComparisonSet requires clarification or fallback reason"
            )
        return self
