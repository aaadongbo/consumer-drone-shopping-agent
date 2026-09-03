"""Internal storefront view-model adapters.

These types are local presentation models. They are derived from existing
public envelopes plus local UI state and are not API DTOs.
"""

from storefront.view_model import (
    ConstraintPresentationState,
    FallbackView,
    RenderStatus,
    StorefrontPendingClarification,
    StorefrontTargetDisplay,
    StorefrontTransportRejection,
    StorefrontTurnView,
    StorefrontUiState,
    build_storefront_turn_view,
    build_transport_rejection_view,
)

__all__ = [
    "ConstraintPresentationState",
    "FallbackView",
    "RenderStatus",
    "StorefrontPendingClarification",
    "StorefrontTargetDisplay",
    "StorefrontTransportRejection",
    "StorefrontTurnView",
    "StorefrontUiState",
    "build_storefront_turn_view",
    "build_transport_rejection_view",
]
