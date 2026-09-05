"""Contract checks for the live Shopify adapter's public and wire boundaries."""

import inspect
from dataclasses import asdict, fields
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter

from backend.common import AttributeValue, ProductRecord, ToolResult, VariantRecord
from backend.shopify import (
    RealShopifyReadAdapter,
    ShopifyReadTransport,
    ShopifyTokenProvider,
    ShopifyTransportResult,
)

pytestmark = pytest.mark.contract

NOW = datetime(2026, 9, 5, 6, 30, tzinfo=UTC)
STORE = "bys-user-store-578412-7a11gk0u.myshopify.com"
PRODUCT = "9278460821642"
VARIANT = "50107426603146"


class ContractTransport:
    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        return ShopifyTransportResult(
            payload={
                "product": {
                    "id": product_id,
                    "title": "DJI Air 3",
                    "variants": [
                        {
                            "id": VARIANT,
                            "product_id": product_id,
                            "title": "Default Title",
                        }
                    ],
                }
            }
        )

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        return ShopifyTransportResult(
            payload={
                "variants": [
                    {
                        "id": VARIANT,
                        "product_id": product_id,
                        "title": "Default Title",
                    }
                ]
            }
        )

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        return ShopifyTransportResult(
            payload={
                "variant": {
                    "id": variant_id,
                    "product_id": product_id,
                    "price": "3299.00",
                    "inventory_quantity": 32,
                    "available_for_sale": True,
                }
            }
        )


def test_typed_transport_surface_has_only_three_read_queries() -> None:
    methods = {
        name
        for name, member in inspect.getmembers(ShopifyReadTransport, inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {"read_product", "read_variants", "read_commerce_state"}

    token_methods = {
        name
        for name, member in inspect.getmembers(ShopifyTokenProvider, inspect.isfunction)
        if not name.startswith("_")
    }
    assert token_methods == {"get_access_token"}


def test_adapter_surface_has_no_mutation_or_generic_dispatcher() -> None:
    public_names = {
        name.lower()
        for name, member in inspect.getmembers(RealShopifyReadAdapter)
        if not name.startswith("_")
    }
    assert {
        "get_products",
        "get_variants",
        "refresh_commerce_state",
        "call_ledger",
        "last_stop_reason",
        "write_call_count",
    } <= public_names
    prohibited = {
        "create",
        "update",
        "delete",
        "mutate",
        "mutation",
        "cart",
        "order",
        "customer",
        "inventory_update",
        "execute",
        "invoke",
        "dispatch",
    }
    assert not any(token in name for name in public_names for token in prohibited)


def test_existing_public_tool_contract_round_trips_live_adapter_results() -> None:
    adapter = RealShopifyReadAdapter(
        transport=ContractTransport(),
        clock=lambda: NOW,
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
        max_read_calls=3,
    )

    product = adapter.get_products(store_id=STORE, product_id=PRODUCT)
    variants = adapter.get_variants(
        store_id=STORE, product_id=PRODUCT, variant_id=VARIANT
    )
    commerce = adapter.refresh_commerce_state(
        store_id=STORE, product_id=PRODUCT, variant_id=VARIANT
    )

    assert (
        TypeAdapter(ToolResult[list[ProductRecord]]).validate_json(
            product.to_wire_json()
        )
        == product
    )
    assert (
        TypeAdapter(ToolResult[list[VariantRecord]]).validate_json(
            variants.to_wire_json()
        )
        == variants
    )
    assert (
        TypeAdapter(ToolResult[dict[str, AttributeValue]]).validate_json(
            commerce.to_wire_json()
        )
        == commerce
    )
    assert adapter.write_call_count == 0
    assert all(entry.classification.value == "read" for entry in adapter.call_ledger)


def test_transport_result_repr_hides_payload_and_ledger_contains_metadata_only() -> (
    None
):
    response = ShopifyTransportResult(
        payload={"access_token": "shpat_synthetic", "private": "body"},
        http_status=200,
    )
    assert "shpat_synthetic" not in repr(response)
    assert "body" not in repr(response)

    adapter = RealShopifyReadAdapter(
        transport=ContractTransport(),
        clock=lambda: NOW,
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
    )
    adapter.get_products(store_id=STORE, product_id=PRODUCT)
    ledger_entry = adapter.call_ledger[0]
    assert {field.name for field in fields(ledger_entry)} == {
        "sequence",
        "operation",
        "store_id",
        "product_id",
        "variant_id",
        "classification",
    }
    ledger_values = asdict(ledger_entry)
    assert not any(
        forbidden in ledger_values
        for forbidden in ("access_token", "private", "headers", "response")
    )


def test_no_write_count_is_constant_zero() -> None:
    adapter = RealShopifyReadAdapter(transport=ContractTransport())
    assert adapter.write_call_count == 0
    assert not any(
        "write" in name.lower()
        for name in dir(adapter)
        if callable(getattr(adapter, name, None))
    )
