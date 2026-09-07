"""Integration of the typed HTTP boundary with the read-only adapter."""

import json
from urllib.parse import urlsplit

import pytest

from backend.common import ToolStatus
from backend.shopify import (
    RealShopifyReadAdapter,
    ShopifyTransportResult,
    UrllibShopifyReadTransport,
)

pytestmark = pytest.mark.integration

STORE = "bys-user-store-578412-7a11gk0u.myshopify.com"
PRODUCTS = {
    "9278460821642": ("50107426603146", "DJI Air 3", 3299, 32),
    "9278439719050": ("50107364901002", "DJI Mavic 3", 5299, 18),
    "9278439686282": ("50107364802698", "DJI Mini 3", 2199, 12),
}


class Response:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self._body = body

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class TokenProvider:
    def get_access_token(self) -> str:
        return "shpat_synthetic"


class RecordedResponseOpener:
    """Serve minimal synthetic response shapes without persisting Shopify bodies."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def open(self, request: object, timeout: float) -> Response:
        self.calls.append((request.full_url, timeout))
        path = urlsplit(request.full_url).path
        parts = path.split("/")
        if "/variants/" in path:
            variant_id = parts[5].removesuffix(".json")
            product_id = next(
                product_id
                for product_id, details in PRODUCTS.items()
                if details[0] == variant_id
            )
            _variant_id, title, price, inventory = PRODUCTS[product_id]
            body = {
                "variant": {
                    "id": variant_id,
                    "product_id": product_id,
                    "title": "Default Title",
                    "price": f"{price}.00",
                    "inventory_quantity": inventory,
                    "available_for_sale": inventory > 0,
                }
            }
        else:
            product_id = parts[5].removesuffix(".json")
            variant_id, title, price, inventory = PRODUCTS[product_id]
            body = {
                "product": {
                    "id": product_id,
                    "title": title,
                    "status": "draft",
                    "variants": [
                        {
                            "id": variant_id,
                            "product_id": product_id,
                            "title": "Default Title",
                        }
                    ],
                }
            }
        return Response(json.dumps(body).encode("utf-8"))


def test_three_approved_products_round_trip_through_typed_read_transport() -> None:
    opener = RecordedResponseOpener()
    transport = UrllibShopifyReadTransport(
        token_provider=TokenProvider(),
        opener=opener,
        timeout_seconds=5.0,
    )
    adapter = RealShopifyReadAdapter(
        transport=transport,
        approved_store_id=STORE,
        approved_variant_ids={
            product_id: details[0] for product_id, details in PRODUCTS.items()
        },
        max_read_calls=6,
    )

    for product_id, (variant_id, title, price, inventory) in PRODUCTS.items():
        product = adapter.get_products(store_id=STORE, product_id=product_id)
        commerce = adapter.refresh_commerce_state(
            store_id=STORE,
            product_id=product_id,
            variant_id=variant_id,
        )

        assert product.status is ToolStatus.SUCCESS
        assert product.data is not None
        assert product.data[0].display_title == title
        assert product.data[0].variant_ids == [variant_id]
        assert commerce.status is ToolStatus.SUCCESS
        assert commerce.data is not None
        assert commerce.data["price"].value == price
        assert commerce.data["inventory"].value == inventory
        assert commerce.data["availability"].value is True

    assert len(opener.calls) == 6
    assert all(timeout == 5.0 for _, timeout in opener.calls)
    assert all("/admin/api/2026-07/" in url for url, _ in opener.calls)
    assert all(entry.classification.value == "read" for entry in adapter.call_ledger)
    assert adapter.write_call_count == 0


def test_transport_response_envelope_is_not_exposed_as_adapter_ledger_data() -> None:
    result = ShopifyTransportResult(payload={"product": {"id": "9278460821642"}})
    assert result.payload is not None
    assert "9278460821642" not in repr(result)
