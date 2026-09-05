"""S11-T04 unit coverage for the restricted intent adapter boundary."""

from __future__ import annotations

import pytest

from backend.agent import (
    IntentAdapterBudget,
    IntentAdapterSignal,
    IntentDecisionSource,
    IntentRoute,
    IntentSignalStatus,
    RestrictedIntentRouter,
)
from backend.common import ConversationRef, PageContext, TurnRequest

pytestmark = pytest.mark.unit


def _request(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version="1.0",
        store_id="store-dji-cn",
        conversation=ConversationRef(
            conversation_id="conversation-1",
            message_id="message-1",
        ),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="mini-4-pro", variant_id="bundle-1"),
    )


class _Adapter:
    def __init__(self, signal: IntentAdapterSignal | BaseException) -> None:
        self.signal = signal
        self.seen_budget: IntentAdapterBudget | None = None

    def route(
        self,
        request: TurnRequest,
        *,
        budget: IntentAdapterBudget,
    ) -> IntentAdapterSignal:
        self.seen_budget = budget
        if isinstance(self.signal, BaseException):
            raise self.signal
        assert request.user_text
        return self.signal


def _router(signal: IntentAdapterSignal | BaseException) -> RestrictedIntentRouter:
    return RestrictedIntentRouter(
        adapter=_Adapter(signal),
        budget=IntentAdapterBudget(timeout_ms=25, max_model_tokens=12),
    )


def test_default_router_uses_deterministic_fallback_without_provider() -> None:
    router = RestrictedIntentRouter(
        budget=IntentAdapterBudget(timeout_ms=25, max_model_tokens=12)
    )

    dynamic = router.decide(_request("这款现在多少钱？"))
    static = router.decide(_request("包装里有什么？"))

    assert dynamic.route is IntentRoute.COMMERCE_FACT
    assert static.route is IntentRoute.STATIC_PRODUCT_QA
    assert dynamic.source is IntentDecisionSource.DETERMINISTIC_FALLBACK


def test_high_confidence_adapter_route_is_accepted_without_facts() -> None:
    decision = _router(
        IntentAdapterSignal(
            status=IntentSignalStatus.ROUTED,
            route=IntentRoute.STATIC_PRODUCT_QA,
            confidence=0.91,
            token_count=10,
            metadata={"provider": "fake", "raw_response": "must redact"},
        )
    ).decide(_request("包装里有什么？"))

    assert decision.route is IntentRoute.STATIC_PRODUCT_QA
    assert decision.source is IntentDecisionSource.ADAPTER
    assert decision.metadata == {"provider": "fake", "raw_response": "[REDACTED]"}


@pytest.mark.parametrize(
    "signal",
    [
        IntentAdapterSignal(
            status=IntentSignalStatus.ROUTED,
            route=IntentRoute.STATIC_PRODUCT_QA,
            confidence=0.69,
            token_count=1,
        ),
        IntentAdapterSignal(
            status=IntentSignalStatus.ROUTED,
            route=IntentRoute.STATIC_PRODUCT_QA,
            confidence=0.99,
            token_count=13,
        ),
        IntentAdapterSignal(status=IntentSignalStatus.PROVIDER_FAILURE),
        TimeoutError("simulated timeout"),
        RuntimeError("simulated provider failure"),
    ],
)
def test_rejected_or_failed_adapter_routes_use_deterministic_fallback(
    signal: IntentAdapterSignal | BaseException,
) -> None:
    decision = _router(signal).decide(_request("这款现在多少钱？"))

    assert decision.route is IntentRoute.COMMERCE_FACT
    assert decision.source is IntentDecisionSource.DETERMINISTIC_FALLBACK
    assert decision.confidence is None


def test_unsupported_intent_returns_safe_fallback() -> None:
    decision = _router(
        IntentAdapterSignal(
            status=IntentSignalStatus.UNSUPPORTED_INTENT,
            metadata={"prompt": "do not store", "provider": "fake"},
        )
    ).decide(_request("帮我查询订单状态。"))

    assert decision.route is IntentRoute.SAFE_FALLBACK
    assert decision.source is IntentDecisionSource.SAFE_FALLBACK
    assert decision.reason is IntentSignalStatus.UNSUPPORTED_INTENT
    assert decision.metadata == {"prompt": "[REDACTED]", "provider": "fake"}


def test_adapter_receives_only_hard_budget_values() -> None:
    adapter = _Adapter(
        IntentAdapterSignal(
            status=IntentSignalStatus.ROUTED,
            route=IntentRoute.COMMERCE_FACT,
            confidence=0.9,
            token_count=1,
        )
    )
    router = RestrictedIntentRouter(
        adapter=adapter,
        budget=IntentAdapterBudget(timeout_ms=123, max_model_tokens=456),
    )

    router.decide(_request("这款现在多少钱？"))

    assert adapter.seen_budget == IntentAdapterBudget(
        timeout_ms=123,
        max_model_tokens=456,
    )
