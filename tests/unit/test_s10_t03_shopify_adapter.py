"""Unit coverage for the injected, read-only Shopify adapter."""

from datetime import UTC, datetime
from subprocess import CompletedProcess

import pytest

from backend.common import ToolErrorCode, ToolStatus, TraceOperation
from backend.shopify import (
    MacOSKeychainAccessTokenProvider,
    RealShopifyReadAdapter,
    ShopifyAdapterStopReason,
    ShopifyTransportFailure,
    ShopifyTransportResult,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 6, 30, tzinfo=UTC)
STORE = "bys-user-store-578412-7a11gk0u.myshopify.com"
PRODUCT = "9278460821642"
VARIANT = "50107426603146"


def product_response(
    *, product_id: str = PRODUCT, variant_id: str = VARIANT
) -> ShopifyTransportResult:
    return ShopifyTransportResult(
        payload={
            "product": {
                "id": product_id,
                "title": "DJI Air 3",
                "status": "draft",
                "variants": [
                    {
                        "id": variant_id,
                        "product_id": product_id,
                        "title": "Default Title",
                        "option1": "Default Title",
                    }
                ],
            }
        },
        http_status=200,
    )


def variants_response(
    *, product_id: str = PRODUCT, variant_id: str = VARIANT
) -> ShopifyTransportResult:
    return ShopifyTransportResult(
        payload={
            "variants": [
                {
                    "id": variant_id,
                    "product_id": product_id,
                    "title": "Default Title",
                    "option1": "Default Title",
                }
            ]
        },
        http_status=200,
    )


def commerce_response(
    *, product_id: str = PRODUCT, variant_id: str = VARIANT
) -> ShopifyTransportResult:
    return ShopifyTransportResult(
        payload={
            "variant": {
                "id": variant_id,
                "product_id": product_id,
                "title": "Default Title",
                "price": "3299.00",
                "inventory_quantity": 32,
                "inventory_policy": "deny",
            }
        },
        http_status=200,
    )


def commerce_fallback_product_response() -> ShopifyTransportResult:
    return ShopifyTransportResult(
        payload={
            "product": {
                "id": PRODUCT,
                "title": "DJI Air 3",
                "variants": [
                    {
                        "id": VARIANT,
                        "product_id": PRODUCT,
                        "title": "Default Title",
                        "price": "3299.00",
                        "inventory_quantity": 32,
                        "inventory_policy": "deny",
                    }
                ],
            }
        },
        http_status=200,
    )


class StaticTransport:
    def __init__(
        self,
        *,
        product: ShopifyTransportResult | object = product_response(),
        variants: ShopifyTransportResult | object = variants_response(),
        commerce: ShopifyTransportResult | object = commerce_response(),
    ) -> None:
        self.product = product
        self.variants = variants
        self.commerce = commerce
        self.calls: list[tuple[str, str, str, str | None]] = []

    def read_product(self, *, store_id: str, product_id: str):
        self.calls.append(("product", store_id, product_id, None))
        return self.product

    def read_variants(self, *, store_id: str, product_id: str):
        self.calls.append(("variants", store_id, product_id, None))
        return self.variants

    def read_commerce_state(self, *, store_id: str, product_id: str, variant_id: str):
        self.calls.append(("commerce", store_id, product_id, variant_id))
        return self.commerce


def adapter(
    transport: StaticTransport, *, max_read_calls: int = 2
) -> RealShopifyReadAdapter:
    return RealShopifyReadAdapter(
        transport=transport,
        clock=lambda: NOW,
        approved_store_id=STORE,
        approved_variant_ids={PRODUCT: VARIANT},
        max_read_calls=max_read_calls,
    )


def test_normalizes_product_variant_and_current_commerce_with_one_timestamp() -> None:
    transport = StaticTransport()
    source = adapter(transport, max_read_calls=3)

    product = source.get_products(store_id=STORE, product_id=PRODUCT)
    variants = source.get_variants(store_id=STORE, product_id=PRODUCT)
    commerce = source.refresh_commerce_state(
        store_id=STORE, product_id=PRODUCT, variant_id=VARIANT
    )

    assert product.status is ToolStatus.SUCCESS
    assert product.data is not None
    assert product.data[0].product_id == PRODUCT
    assert product.data[0].variant_ids == [VARIANT]
    assert variants.data is not None
    assert [item.variant_id for item in variants.data] == [VARIANT]
    assert commerce.status is ToolStatus.SUCCESS
    assert commerce.data is not None
    assert commerce.data["price"].value == 3299
    assert commerce.data["inventory"].value == 32
    assert commerce.data["availability"].value is True
    assert commerce.observed_at == NOW
    assert {item.observed_at for item in commerce.data.values()} == {NOW}
    assert {item.source_ref for item in commerce.data.values()} == {
        f"shopify://{STORE}/products/{PRODUCT}/variants/{VARIANT}/commerce"
        f"#commerce.{field}"
        for field in ("price", "inventory", "availability")
    }
    assert [entry.operation for entry in source.call_ledger] == [
        TraceOperation.GET_PRODUCTS,
        TraceOperation.GET_VARIANTS,
        TraceOperation.REFRESH_COMMERCE_STATE,
    ]
    assert all(entry.classification.value == "read" for entry in source.call_ledger)
    assert source.write_call_count == 0


def test_commerce_not_found_uses_one_exact_product_read_within_budget() -> None:
    transport = StaticTransport(
        product=commerce_fallback_product_response(),
        commerce=ShopifyTransportResult(failure=ShopifyTransportFailure.NOT_FOUND),
    )
    source = adapter(transport)

    result = source.refresh_commerce_state(
        store_id=STORE, product_id=PRODUCT, variant_id=VARIANT
    )

    assert result.status is ToolStatus.SUCCESS
    assert result.data is not None
    assert result.data["price"].value == 3299
    assert [entry.operation for entry in source.call_ledger] == [
        TraceOperation.REFRESH_COMMERCE_STATE,
        TraceOperation.GET_PRODUCTS,
    ]
    assert [call[0] for call in transport.calls] == ["commerce", "product"]
    assert source.last_stop_reason is None
    assert source.write_call_count == 0


def test_store_mismatch_stops_before_transport_and_does_not_pollute_ledger() -> None:
    transport = StaticTransport()
    source = adapter(transport)

    result = source.get_products(store_id="foreign.myshopify.com", product_id=PRODUCT)

    assert result.status is ToolStatus.ERROR
    assert result.error_code is ToolErrorCode.PRODUCT_NOT_FOUND
    assert source.last_stop_reason is ShopifyAdapterStopReason.IDENTITY_MISMATCH
    assert transport.calls == []
    assert source.call_ledger == ()
    assert source.write_call_count == 0


def test_approved_variant_mismatch_stops_before_transport() -> None:
    transport = StaticTransport()
    source = adapter(transport)

    result = source.refresh_commerce_state(
        store_id=STORE, product_id=PRODUCT, variant_id="50107426603147"
    )

    assert result.status is ToolStatus.ERROR
    assert result.error_code is ToolErrorCode.VARIANT_NOT_FOUND
    assert source.last_stop_reason is ShopifyAdapterStopReason.IDENTITY_MISMATCH
    assert transport.calls == []
    assert source.call_ledger == ()


def test_default_two_read_budget_stops_before_third_external_call() -> None:
    transport = StaticTransport()
    source = adapter(transport)

    source.get_products(store_id=STORE, product_id=PRODUCT)
    source.refresh_commerce_state(
        store_id=STORE, product_id=PRODUCT, variant_id=VARIANT
    )
    result = source.get_variants(store_id=STORE, product_id=PRODUCT)

    assert result.status is ToolStatus.ERROR
    assert result.error_code is ToolErrorCode.VARIANT_NOT_FOUND
    assert source.last_stop_reason is ShopifyAdapterStopReason.SHOPIFY_READ_CALL_LIMIT
    assert len(transport.calls) == 2
    assert len(source.call_ledger) == 2
    assert source.write_call_count == 0


@pytest.mark.parametrize("kwargs", [{"max_read_calls": 0}, {"max_attempts": 2}])
def test_adapter_rejects_unbounded_or_retrying_configuration(
    kwargs: dict[str, int],
) -> None:
    with pytest.raises(ValueError):
        RealShopifyReadAdapter(transport=StaticTransport(), **kwargs)


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_reason", "retryable"),
    [
        (
            ShopifyTransportFailure.TIMEOUT,
            ToolErrorCode.TIMEOUT,
            ShopifyAdapterStopReason.TIMEOUT,
            True,
        ),
        (
            ShopifyTransportFailure.RATE_LIMITED,
            ToolErrorCode.RATE_LIMITED,
            ShopifyAdapterStopReason.RATE_LIMITED,
            True,
        ),
        (
            ShopifyTransportFailure.UNAUTHORIZED,
            ToolErrorCode.UNAUTHORIZED,
            ShopifyAdapterStopReason.UNAUTHORIZED,
            False,
        ),
        (
            ShopifyTransportFailure.NOT_FOUND,
            ToolErrorCode.PRODUCT_NOT_FOUND,
            ShopifyAdapterStopReason.NOT_FOUND,
            False,
        ),
        (
            ShopifyTransportFailure.NETWORK_ERROR,
            ToolErrorCode.PRODUCT_NOT_FOUND,
            ShopifyAdapterStopReason.NETWORK_FAILURE,
            False,
        ),
    ],
)
def test_transport_failures_are_safe_and_distinguishable(
    failure: ShopifyTransportFailure,
    expected_code: ToolErrorCode,
    expected_reason: ShopifyAdapterStopReason,
    retryable: bool,
) -> None:
    transport = StaticTransport(
        product=ShopifyTransportResult(failure=failure, http_status=503)
    )
    source = adapter(transport)

    result = source.get_products(store_id=STORE, product_id=PRODUCT)

    assert result.status is ToolStatus.ERROR
    assert result.data is None
    assert result.error_code is expected_code
    assert result.retryable is retryable
    assert source.last_stop_reason is expected_reason
    assert "shpat_" not in repr(result)
    assert source.write_call_count == 0


def test_empty_transport_envelope_is_malformed_instead_of_raising() -> None:
    source = adapter(StaticTransport(product=ShopifyTransportResult()))

    result = source.get_products(store_id=STORE, product_id=PRODUCT)

    assert result.status is ToolStatus.ERROR
    assert source.last_stop_reason is ShopifyAdapterStopReason.MALFORMED_RESPONSE
    assert source.write_call_count == 0


@pytest.mark.parametrize(
    "response",
    [
        ShopifyTransportResult(payload={"product": {"id": "foreign"}}),
        ShopifyTransportResult(payload={"product": {"id": PRODUCT, "title": ""}}),
        object(),
    ],
)
def test_product_identity_and_shape_fail_closed(response: object) -> None:
    source = adapter(StaticTransport(product=response))

    result = source.get_products(store_id=STORE, product_id=PRODUCT)

    assert result.status is ToolStatus.ERROR
    assert source.last_stop_reason in {
        ShopifyAdapterStopReason.IDENTITY_MISMATCH,
        ShopifyAdapterStopReason.MALFORMED_RESPONSE,
    }
    assert result.data is None


def test_commerce_partial_preserves_current_facts_and_explicit_missing_field() -> None:
    partial = commerce_response()
    assert partial.payload is not None
    partial.payload["variant"]["available_for_sale"] = True
    del partial.payload["variant"]["inventory_quantity"]
    source = adapter(StaticTransport(commerce=partial))

    result = source.refresh_commerce_state(
        store_id=STORE, product_id=PRODUCT, variant_id=VARIANT
    )

    assert result.status is ToolStatus.PARTIAL
    assert result.error_code is ToolErrorCode.PARTIAL_RESULT
    assert result.missing_fields == ["inventory"]
    assert result.data is not None
    assert result.data["price"].value == 3299
    assert result.data["availability"].value is True
    assert result.observed_at == NOW
    assert {item.observed_at for item in result.data.values()} == {NOW}
    assert source.last_stop_reason is ShopifyAdapterStopReason.MISSING_FIELD


def test_keychain_provider_uses_exact_lookup_and_redacts_failures() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(argv: list[str], **kwargs: object) -> CompletedProcess[str]:
        calls.append((argv, kwargs))
        return CompletedProcess(argv, 0, stdout="shpat_test-token\n", stderr="")

    provider = MacOSKeychainAccessTokenProvider(
        service="consumer-drone-agent.shopify.smoke.access-token",
        account="bys-user-store-578412",
        runner=runner,
    )

    assert provider.get_access_token() == "shpat_test-token"
    assert calls == [
        (
            [
                "/usr/bin/security",
                "find-generic-password",
                "-s",
                "consumer-drone-agent.shopify.smoke.access-token",
                "-a",
                "bys-user-store-578412",
                "-w",
            ],
            {"capture_output": True, "text": True, "check": False},
        )
    ]
