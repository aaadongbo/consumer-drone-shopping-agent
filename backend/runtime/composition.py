"""Explicit closed-beta composition boundary for S11."""

from __future__ import annotations

from dataclasses import dataclass

from backend.agent import IntentAdapterBudget, ProductRagBudget, ProductRagRetriever
from backend.application.pilot_composition import (
    PilotComposition,
    PilotCompositionConfig,
    PilotMode,
    build_pilot_composition,
)
from backend.catalog import PilotDataReadinessReport
from backend.runtime.config import ReleaseConfig, ReleaseConfigError
from backend.shopify import RealShopifyReadAdapter, ShopifyReadPort


@dataclass(frozen=True, slots=True)
class ReleaseDependencies:
    """Already-constructed adapters injected by the runtime entrypoint."""

    shopify: ShopifyReadPort
    static_retriever: ProductRagRetriever
    readiness: PilotDataReadinessReport


def build_closed_beta_composition(
    config: ReleaseConfig,
    dependencies: ReleaseDependencies,
) -> PilotComposition:
    """Build only the explicit read-only pilot path; never fall back to fixtures."""

    if config.release_mode != "closed_beta":
        raise ReleaseConfigError("closed-beta release mode is required")
    if not isinstance(dependencies.shopify, RealShopifyReadAdapter):
        raise ReleaseConfigError("closed-beta requires the live read adapter")
    if not dependencies.readiness.ready:
        raise ReleaseConfigError("pilot readiness is not accepted")
    if dependencies.readiness.store_id != config.store_id:
        raise ReleaseConfigError("pilot readiness scope does not match config")
    rag_budget = ProductRagBudget(
        max_action_rounds=config.max_action_rounds,
        max_tool_calls=config.max_tool_calls_per_turn,
        max_model_tokens=config.max_model_tokens_per_turn,
    )
    return build_pilot_composition(
        PilotCompositionConfig(
            mode=PilotMode.PILOT,
            store_id=config.store_id,
            shopify=dependencies.shopify,
            static_retriever=dependencies.static_retriever,
            readiness=dependencies.readiness,
            rag_budget=rag_budget,
            intent_budget=IntentAdapterBudget(
                timeout_ms=config.request_timeout_ms,
                max_model_tokens=config.max_model_tokens_per_turn,
            ),
        )
    )


__all__ = ["ReleaseDependencies", "build_closed_beta_composition"]
