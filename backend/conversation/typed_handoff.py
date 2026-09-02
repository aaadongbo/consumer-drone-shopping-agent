"""Slice-local typed handoff boundary for non-single-object targets."""

from enum import StrEnum
from typing import Literal

from backend.common.contracts import WireModel
from backend.conversation.target_resolution import (
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)


class HandoffRoute(StrEnum):
    COMPARISON = "COMPARISON"
    RECOMMENDATION = "RECOMMENDATION"
    STORE_SUPPORT = "STORE_SUPPORT"
    CLARIFICATION = "CLARIFICATION"


class TypedHandoff(WireModel):
    """A typed, non-executing destination for a resolved turn target."""

    route: HandoffRoute
    target: TurnTarget
    reason: str
    downstream_execution_allowed: Literal[False] = False


class TypedHandoffRouter:
    """Classify handoff targets without invoking any downstream capability."""

    def route(self, resolution: TargetResolution) -> TypedHandoff:
        target = resolution.turn_target
        if target.kind is TurnTargetKind.COMPARISON_SET:
            return TypedHandoff(
                route=HandoffRoute.COMPARISON,
                target=target,
                reason="comparison target preserves per-member provenance",
            )
        if target.kind is TurnTargetKind.RECOMMENDATION_TASK:
            return TypedHandoff(
                route=HandoffRoute.RECOMMENDATION,
                target=target,
                reason="recommendation remains an unfiltered store-wide task",
            )
        if target.kind is TurnTargetKind.STORE_SUPPORT:
            return TypedHandoff(
                route=HandoffRoute.STORE_SUPPORT,
                target=target,
                reason="support intent is not a product-fact query",
            )
        if target.kind is TurnTargetKind.NEEDS_CLARIFICATION:
            return TypedHandoff(
                route=HandoffRoute.CLARIFICATION,
                target=target,
                reason=target.clarification_reason or "target needs clarification",
            )
        raise ValueError("SINGLE_OBJECT targets must enter the Product Fact flow")
