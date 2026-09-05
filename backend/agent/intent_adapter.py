"""Restricted intent adapter boundary for closed-beta routing.

The adapter can suggest only bounded route candidates.  It cannot emit product
facts, mutate identity, change constraints, call tools, or bypass downstream
Evidence gates.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from backend.common import TurnRequest
from backend.rag import is_dynamic_commerce_question


class IntentRoute(StrEnum):
    COMMERCE_FACT = "COMMERCE_FACT"
    STATIC_PRODUCT_QA = "STATIC_PRODUCT_QA"
    SAFE_FALLBACK = "SAFE_FALLBACK"


class IntentSignalStatus(StrEnum):
    ROUTED = "ROUTED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UNSUPPORTED_INTENT = "UNSUPPORTED_INTENT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class IntentDecisionSource(StrEnum):
    ADAPTER = "ADAPTER"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"
    SAFE_FALLBACK = "SAFE_FALLBACK"


@dataclass(frozen=True, slots=True)
class IntentAdapterBudget:
    timeout_ms: int
    max_model_tokens: int


@dataclass(frozen=True, slots=True)
class IntentAdapterSignal:
    status: IntentSignalStatus
    route: IntentRoute | None = None
    confidence: float | None = None
    token_count: int = 0
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class IntentRoutingDecision:
    route: IntentRoute
    source: IntentDecisionSource
    reason: IntentSignalStatus
    confidence: float | None = None
    metadata: Mapping[str, object] | None = None


class RestrictedIntentAdapter(Protocol):
    """Optional provider/test double surface for route candidates only."""

    def route(
        self,
        request: TurnRequest,
        *,
        budget: IntentAdapterBudget,
    ) -> IntentAdapterSignal: ...


class RestrictedIntentRouter:
    """Bound optional adapter output before falling back deterministically."""

    def __init__(
        self,
        *,
        budget: IntentAdapterBudget,
        adapter: RestrictedIntentAdapter | None = None,
        minimum_confidence: float = 0.70,
        deterministic_classifier: Callable[[str], bool] = is_dynamic_commerce_question,
    ) -> None:
        if budget.timeout_ms <= 0 or budget.max_model_tokens <= 0:
            raise ValueError("intent adapter budget must be positive")
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum confidence must be between 0 and 1")
        self._adapter = adapter
        self._budget = budget
        self._minimum_confidence = minimum_confidence
        self._deterministic_classifier = deterministic_classifier

    def decide(self, request: TurnRequest) -> IntentRoutingDecision:
        if self._adapter is None:
            return self._deterministic(request, IntentSignalStatus.ROUTED)
        try:
            signal = self._adapter.route(request, budget=self._budget)
        except TimeoutError:
            return self._deterministic(request, IntentSignalStatus.TIMEOUT)
        except Exception:
            return self._deterministic(request, IntentSignalStatus.PROVIDER_FAILURE)

        accepted = self._accepted_adapter_signal(signal)
        if accepted is not None:
            return accepted
        if signal.status is IntentSignalStatus.UNSUPPORTED_INTENT:
            return IntentRoutingDecision(
                route=IntentRoute.SAFE_FALLBACK,
                source=IntentDecisionSource.SAFE_FALLBACK,
                reason=IntentSignalStatus.UNSUPPORTED_INTENT,
                metadata=_safe_metadata(signal.metadata),
            )
        return self._deterministic(request, signal.status)

    def _accepted_adapter_signal(
        self, signal: IntentAdapterSignal
    ) -> IntentRoutingDecision | None:
        if signal.status is not IntentSignalStatus.ROUTED:
            return None
        if signal.route is None:
            return None
        if signal.route is IntentRoute.SAFE_FALLBACK:
            return IntentRoutingDecision(
                route=IntentRoute.SAFE_FALLBACK,
                source=IntentDecisionSource.ADAPTER,
                reason=IntentSignalStatus.ROUTED,
                confidence=signal.confidence,
                metadata=_safe_metadata(signal.metadata),
            )
        if signal.confidence is None or signal.confidence < self._minimum_confidence:
            return None
        if signal.token_count > self._budget.max_model_tokens:
            return None
        return IntentRoutingDecision(
            route=signal.route,
            source=IntentDecisionSource.ADAPTER,
            reason=IntentSignalStatus.ROUTED,
            confidence=signal.confidence,
            metadata=_safe_metadata(signal.metadata),
        )

    def _deterministic(
        self, request: TurnRequest, reason: IntentSignalStatus
    ) -> IntentRoutingDecision:
        route = (
            IntentRoute.COMMERCE_FACT
            if self._deterministic_classifier(request.user_text)
            else IntentRoute.STATIC_PRODUCT_QA
        )
        return IntentRoutingDecision(
            route=route,
            source=IntentDecisionSource.DETERMINISTIC_FALLBACK,
            reason=reason,
        )


def _safe_metadata(metadata: Mapping[str, object] | None) -> Mapping[str, object]:
    if metadata is None:
        return {}
    safe: dict[str, object] = {}
    for key, value in metadata.items():
        key_text = str(key)
        if any(
            fragment in key_text.casefold()
            for fragment in ("credential", "prompt", "raw", "secret", "token")
        ):
            safe[key_text] = "[REDACTED]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key_text] = value
        else:
            safe[key_text] = "[OMITTED]"
    return safe


__all__ = [
    "IntentAdapterBudget",
    "IntentAdapterSignal",
    "IntentDecisionSource",
    "IntentRoute",
    "IntentRoutingDecision",
    "IntentSignalStatus",
    "RestrictedIntentAdapter",
    "RestrictedIntentRouter",
]
