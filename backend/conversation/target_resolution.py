"""Slice-local target-resolution contracts for the Slice 3 golden matrix.

These models deliberately do not change the existing public TurnRequest or
AnswerEnvelope wire schemas.  They express the internal result that later
Slice 3 tasks will resolve from a request, page context, and conversation
state.
"""

from enum import StrEnum
from typing import Final, Literal

from pydantic import model_validator

from backend.common import SCHEMA_VERSION, ObjectScope
from backend.common.contracts import WireModel

type SchemaVersion = Literal["1.0"]

_SINGLE_OBJECT_SOURCES: Final = {
    "EXPLICIT",
    "CONFIRMED_CONTEXT",
    "PAGE_CONTEXT",
}


class ResolutionSource(StrEnum):
    """Identity source for one resolved object, never a ranking signal."""

    EXPLICIT = "EXPLICIT"
    CONFIRMED_CONTEXT = "CONFIRMED_CONTEXT"
    PAGE_CONTEXT = "PAGE_CONTEXT"
    UNRESOLVED = "UNRESOLVED"


class ContextAction(StrEnum):
    """The only state actions a later Slice 3 reducer may consume."""

    KEEP = "KEEP"
    AWAIT_CONFIRMATION = "AWAIT_CONFIRMATION"
    SWITCH_CONFIRMED = "SWITCH_CONFIRMED"


class TurnTargetKind(StrEnum):
    SINGLE_OBJECT = "SINGLE_OBJECT"
    COMPARISON_SET = "COMPARISON_SET"
    RECOMMENDATION_TASK = "RECOMMENDATION_TASK"
    STORE_SUPPORT = "STORE_SUPPORT"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class ComparisonMember(WireModel):
    """One independently scoped comparison member and its provenance."""

    scope: ObjectScope
    provenance: ResolutionSource

    @model_validator(mode="after")
    def validate_provenance(self) -> "ComparisonMember":
        if self.provenance is ResolutionSource.UNRESOLVED:
            raise ValueError("comparison members require resolved provenance")
        return self


class TurnTarget(WireModel):
    """Immutable, typed target for a single user turn."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    kind: TurnTargetKind
    object_scope: ObjectScope | None = None
    comparison_members: tuple[ComparisonMember, ...] = ()
    clarification_reason: str | None = None
    clarification_candidates: tuple[ObjectScope, ...] = ()

    @model_validator(mode="after")
    def validate_target_shape(self) -> "TurnTarget":
        if self.kind is TurnTargetKind.SINGLE_OBJECT:
            if self.object_scope is None:
                raise ValueError("SINGLE_OBJECT requires object_scope")
            if self.comparison_members:
                raise ValueError("SINGLE_OBJECT must omit comparison_members")
        elif self.kind is TurnTargetKind.COMPARISON_SET:
            if self.object_scope is not None:
                raise ValueError("COMPARISON_SET must omit object_scope")
            if not 2 <= len(self.comparison_members) <= 4:
                raise ValueError("COMPARISON_SET requires two to four members")
            scopes = [member.scope for member in self.comparison_members]
            if len(set(scopes)) != len(scopes):
                raise ValueError("COMPARISON_SET members must be unique")
        elif self.kind is TurnTargetKind.NEEDS_CLARIFICATION:
            if self.object_scope is not None or self.comparison_members:
                raise ValueError("NEEDS_CLARIFICATION must omit resolved object fields")
            if self.clarification_reason is None:
                raise ValueError("NEEDS_CLARIFICATION requires clarification_reason")
        else:
            if self.object_scope is not None or self.comparison_members:
                raise ValueError(f"{self.kind} must omit resolved object fields")

        if self.kind is not TurnTargetKind.NEEDS_CLARIFICATION and (
            self.clarification_reason is not None or self.clarification_candidates
        ):
            raise ValueError("only NEEDS_CLARIFICATION may carry clarification data")
        return self


class TargetResolution(WireModel):
    """A validated Slice 3 resolution proposal with no state mutation."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    explicit_references: tuple[ObjectScope, ...] = ()
    turn_target: TurnTarget
    resolution_source: ResolutionSource | None = None
    context_action: ContextAction

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> "TargetResolution":
        target_kind = self.turn_target.kind
        source_supplied = "resolution_source" in self.model_fields_set

        if target_kind is TurnTargetKind.SINGLE_OBJECT:
            if self.resolution_source is None:
                raise ValueError("SINGLE_OBJECT requires resolution_source")
            if self.resolution_source.value not in _SINGLE_OBJECT_SOURCES:
                raise ValueError("SINGLE_OBJECT requires a resolved source")
        elif source_supplied:
            raise ValueError(
                "only SINGLE_OBJECT may carry resolution_source; comparison "
                "provenance is per member"
            )

        if (
            self.context_action
            in {
                ContextAction.AWAIT_CONFIRMATION,
                ContextAction.SWITCH_CONFIRMED,
            }
            and target_kind is not TurnTargetKind.SINGLE_OBJECT
        ):
            raise ValueError("context switch actions require a SINGLE_OBJECT target")
        return self
