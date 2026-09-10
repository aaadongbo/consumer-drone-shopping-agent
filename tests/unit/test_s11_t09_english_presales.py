"""T09 deterministic English routing and pre-sales boundary tests."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.application.slice_1 import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    EnvelopeOutcome,
    PageContext,
    RouteAction,
    RouteIntent,
    TurnRequest,
)
from backend.shopify import RealShopifyReadAdapter, ShopifyTransportResult
from scripts.s11_runtime_entrypoint import create_runtime_app

pytestmark = pytest.mark.unit

STORE = "shopify-store:bys-user-store-578412-7a11gk0u"
PRODUCT = "9278439686282"
VARIANT = "50107364802698"


def _request(text: str, *, variant_id: str | None = VARIANT) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=STORE,
        conversation=ConversationRef(conversation_id="t09", message_id=text),
        user_text=text,
        locale="en-US",
        page_context=PageContext(product_id=PRODUCT, variant_id=variant_id),
    )


class _UsCommerceTransport:
    def read_product(self, *, store_id: str, product_id: str):
        return ShopifyTransportResult(
            payload={
                "product": {
                    "id": product_id,
                    "title": "DJI Mini 3",
                    "variants": [
                        {
                            "id": VARIANT,
                            "product_id": product_id,
                            "title": "Default Title",
                        }
                    ],
                }
            },
            http_status=200,
        )

    def read_variants(self, *, store_id: str, product_id: str):
        return ShopifyTransportResult(
            payload={
                "variants": [
                    {
                        "id": VARIANT,
                        "product_id": product_id,
                        "title": "Default Title",
                    }
                ]
            },
            http_status=200,
        )

    def read_commerce_state(self, *, store_id: str, product_id: str, variant_id: str):
        return ShopifyTransportResult(
            payload={
                "variant": {
                    "id": variant_id,
                    "product_id": product_id,
                    "title": "Default Title",
                    "price": "549.00",
                    "inventory_quantity": 7,
                    "available_for_sale": True,
                }
            },
            http_status=200,
        )


def test_english_commerce_and_variant_questions_are_bounded() -> None:
    interpreter = DeterministicQuestionInterpreter()
    price = interpreter.interpret(_request("What is the current price?"))
    inventory = interpreter.interpret(_request("How many units are in stock?"))
    availability = interpreter.interpret(_request("Is this available?"))
    battery = interpreter.interpret(_request("How many batteries are in the package?"))

    assert price.action is RouteAction.READ_VARIANT_FACT
    assert price.requested_field == "price"
    assert inventory.requested_field == "inventory"
    assert availability.requested_field == "availability"
    assert battery.action is RouteAction.READ_VARIANT_FACT
    assert battery.requested_field == "battery_count"


def test_english_order_and_payment_questions_are_store_support_handoffs() -> None:
    interpreter = DeterministicQuestionInterpreter()
    for text in ("Where is my order?", "Can I get a refund?", "My payment failed"):
        decision = interpreter.interpret(_request(text))
        assert decision.intent is RouteIntent.OUT_OF_SCOPE
        assert decision.action is RouteAction.RETURN_FALLBACK


def test_english_dynamic_answer_is_read_only_and_localized() -> None:
    shopify = RealShopifyReadAdapter(
        transport=_UsCommerceTransport(),
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
        commerce_currency="USD",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )
    service = Slice1ApplicationService(
        shopify=shopify,
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "t09-correlation",
        clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
    )

    payload = service.answer(_request("What is the current price?")).root
    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.text.startswith("The current price")
    assert "USD" in payload.text
    assert payload.evidence[0].fact is not None
    assert payload.evidence[0].fact.unit == "USD"
    assert shopify.write_call_count == 0

    inventory = service.answer(_request("How many units are in stock?")).root
    availability = service.answer(_request("Is this available?")).root
    assert inventory.outcome is EnvelopeOutcome.ANSWER
    assert "inventory" in inventory.text
    assert availability.outcome is EnvelopeOutcome.ANSWER
    assert "available" in availability.text
    assert shopify.write_call_count == 0


def test_product_only_english_variant_question_fails_closed() -> None:
    decision = DeterministicQuestionInterpreter().interpret(
        _request("How many batteries are in the package?", variant_id=None)
    )
    assert decision.action is RouteAction.REQUEST_VARIANT_CLARIFICATION


def test_runtime_health_exposes_redacted_monitoring_signals() -> None:
    response = TestClient(create_runtime_app({})).get("/healthz")
    payload = response.json()
    assert response.status_code == 200
    assert payload["credential_values_exposed"] is False
    assert payload["shopify_write_count"] == 0
    assert payload["monitoring"]["redacted"] is True
    assert payload["monitoring"]["http_5xx"] == 0
    assert "fallback_count" in payload["monitoring"]["signals"]
