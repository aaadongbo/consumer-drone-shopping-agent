"""Contract-shaped checks for the S11 restricted intent adapter boundary."""

from __future__ import annotations

from dataclasses import fields

import pytest

from backend.agent import (
    IntentAdapterBudget,
    IntentAdapterSignal,
    IntentRoute,
    IntentSignalStatus,
    RestrictedIntentAdapter,
)
from backend.common import ConversationRef, PageContext, TurnRequest

pytestmark = pytest.mark.contract


def test_adapter_signal_contract_contains_route_metadata_not_product_facts() -> None:
    names = {field.name for field in fields(IntentAdapterSignal)}

    assert names == {"status", "route", "confidence", "token_count", "metadata"}
    assert not {"answer", "fact", "evidence", "product", "variant"} & names


def test_adapter_budget_contract_is_timeout_and_token_only() -> None:
    assert {field.name for field in fields(IntentAdapterBudget)} == {
        "timeout_ms",
        "max_model_tokens",
    }


def test_adapter_protocol_accepts_deterministic_fake_without_live_provider() -> None:
    class FakeAdapter:
        def route(
            self,
            request: TurnRequest,
            *,
            budget: IntentAdapterBudget,
        ) -> IntentAdapterSignal:
            assert budget.max_model_tokens == 1200
            assert request.store_id == "store-dji-cn"
            return IntentAdapterSignal(
                status=IntentSignalStatus.ROUTED,
                route=IntentRoute.STATIC_PRODUCT_QA,
                confidence=0.9,
            )

    adapter: RestrictedIntentAdapter = FakeAdapter()
    signal = adapter.route(
        TurnRequest(
            schema_version="1.0",
            store_id="store-dji-cn",
            conversation=ConversationRef(
                conversation_id="conversation-1",
                message_id="message-1",
            ),
            user_text="包装里有什么？",
            locale="zh-CN",
            page_context=PageContext(product_id="mini-4-pro"),
        ),
        budget=IntentAdapterBudget(timeout_ms=8000, max_model_tokens=1200),
    )

    assert signal.route is IntentRoute.STATIC_PRODUCT_QA
