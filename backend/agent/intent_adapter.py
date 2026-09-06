"""Restricted intent adapter boundary for closed-beta routing.

The adapter can suggest only bounded route candidates.  It cannot emit product
facts, mutate identity, change constraints, call tools, or bypass downstream
Evidence gates.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from threading import Thread
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
            signal = _validate_signal(self._call_adapter(request))
        except TimeoutError:
            return self._deterministic(request, IntentSignalStatus.TIMEOUT)
        except Exception:
            return self._deterministic(request, IntentSignalStatus.PROVIDER_FAILURE)

        accepted = self._accepted_adapter_signal(request, signal)
        if accepted is not None:
            return accepted
        if signal.status in {
            IntentSignalStatus.UNSUPPORTED_INTENT,
            IntentSignalStatus.BUDGET_EXHAUSTED,
        }:
            return self._safe_fallback(signal.status, signal.metadata)
        return self._deterministic(request, signal.status)

    def _call_adapter(self, request: TurnRequest) -> IntentAdapterSignal:
        """Run a blocking adapter in a daemon worker bounded by the turn budget."""
        adapter = self._adapter
        assert adapter is not None
        result: list[IntentAdapterSignal] = []
        errors: list[Exception] = []

        def invoke() -> None:
            try:
                result.append(adapter.route(request, budget=self._budget))
            except Exception as error:
                errors.append(error)

        worker = Thread(target=invoke, daemon=True)
        worker.start()
        worker.join(self._budget.timeout_ms / 1000)
        if worker.is_alive():
            raise TimeoutError("intent adapter exceeded its time budget")
        if errors:
            raise errors[0]
        if not result:
            raise RuntimeError("intent adapter returned no signal")
        return result[0]

    def _accepted_adapter_signal(
        self, request: TurnRequest, signal: IntentAdapterSignal
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
            return self._safe_fallback(
                IntentSignalStatus.BUDGET_EXHAUSTED, signal.metadata
            )
        if (
            signal.route is IntentRoute.COMMERCE_FACT
            and not self._deterministic_classifier(request.user_text)
        ):
            return None
        return IntentRoutingDecision(
            route=signal.route,
            source=IntentDecisionSource.ADAPTER,
            reason=IntentSignalStatus.ROUTED,
            confidence=signal.confidence,
            metadata=_safe_metadata(signal.metadata),
        )

    def _safe_fallback(
        self,
        reason: IntentSignalStatus,
        metadata: Mapping[str, object] | None,
    ) -> IntentRoutingDecision:
        return IntentRoutingDecision(
            route=IntentRoute.SAFE_FALLBACK,
            source=IntentDecisionSource.SAFE_FALLBACK,
            reason=reason,
            metadata=_safe_metadata(metadata),
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
    """Keep provider metadata entirely outside the routing decision boundary."""
    return {}


def _validate_signal(signal: object) -> IntentAdapterSignal:
    if not isinstance(signal, IntentAdapterSignal):
        raise TypeError("intent adapter returned an invalid signal")
    if not isinstance(signal.status, IntentSignalStatus):
        raise ValueError("intent adapter signal status is invalid")
    if signal.route is not None and not isinstance(signal.route, IntentRoute):
        raise ValueError("intent adapter signal route is invalid")
    confidence = signal.confidence
    if confidence is not None and (
        isinstance(confidence, bool)
        or not isinstance(confidence, Real)
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
    ):
        raise ValueError("intent adapter signal confidence is invalid")
    if (
        isinstance(signal.token_count, bool)
        or not isinstance(signal.token_count, int)
        or signal.token_count < 0
    ):
        raise ValueError("intent adapter signal token count is invalid")
    if signal.metadata is not None and not isinstance(signal.metadata, Mapping):
        raise ValueError("intent adapter signal metadata is invalid")
    return signal


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
