"""Unit coverage for the no-retry Shopify HTTPS transport boundary."""

from collections.abc import Mapping
from subprocess import CompletedProcess
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.shopify import (
    MacOSKeychainAccessTokenProvider,
    ShopifyCredentialError,
    ShopifyTransportFailure,
    UrllibShopifyReadTransport,
)

pytestmark = pytest.mark.unit

STORE = "bys-user-store-578412-7a11gk0u.myshopify.com"


class TokenProvider:
    def __init__(self, value: str = "shpat_synthetic") -> None:
        self.value = value
        self.calls = 0

    def get_access_token(self) -> str:
        self.calls += 1
        return self.value


class Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class Opener:
    def __init__(self, response: Response | BaseException) -> None:
        self.response = response
        self.calls: list[tuple[object, float]] = []

    def open(self, request: object, timeout: float) -> Response:
        self.calls.append((request, timeout))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def transport(
    opener: Opener, *, token_provider: TokenProvider | object | None = None
) -> UrllibShopifyReadTransport:
    return UrllibShopifyReadTransport(
        token_provider=token_provider or TokenProvider(),
        opener=opener,
        timeout_seconds=4.5,
    )


def test_product_read_is_explicit_get_with_bounded_timeout_and_selected_fields() -> (
    None
):
    opener = Opener(Response(b'{"product": {"id": 123}}'))
    provider = TokenProvider()
    result = UrllibShopifyReadTransport(
        token_provider=provider,
        opener=opener,
        timeout_seconds=4.5,
    ).read_product(
        store_id=STORE,
        product_id="gid://shopify/Product/123",
    )

    assert result.failure is None
    assert result.http_status == 200
    assert result.payload == {"product": {"id": 123}}
    assert provider.calls == 1
    assert len(opener.calls) == 1
    request, timeout = opener.calls[0]
    assert timeout == 4.5
    assert request.get_method() == "GET"
    parsed = urlsplit(request.full_url)
    assert parsed.netloc == STORE
    assert parsed.path == "/admin/api/2026-07/products/123.json"
    assert parse_qs(parsed.query)["fields"] == ["id,title,status,published_at,variants"]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert headers["x-shopify-access-token"] == "shpat_synthetic"
    assert headers["accept"] == "application/json"


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (401, ShopifyTransportFailure.UNAUTHORIZED),
        (403, ShopifyTransportFailure.UNAUTHORIZED),
        (404, ShopifyTransportFailure.NOT_FOUND),
        (408, ShopifyTransportFailure.TIMEOUT),
        (429, ShopifyTransportFailure.RATE_LIMITED),
        (500, ShopifyTransportFailure.NETWORK_ERROR),
        (504, ShopifyTransportFailure.TIMEOUT),
    ],
)
def test_http_statuses_map_without_reading_or_recording_error_bodies(
    status: int, failure: ShopifyTransportFailure
) -> None:
    opener = Opener(HTTPError("https://example.invalid", status, "private", {}, None))
    result = transport(opener).read_variants(store_id=STORE, product_id="123")

    assert result.failure is failure
    assert result.http_status == status
    assert result.payload is None
    assert len(opener.calls) == 1
    assert "private" not in repr(result)


def test_timeout_is_returned_after_one_attempt_without_retry() -> None:
    opener = Opener(TimeoutError("timed out"))

    result = transport(opener).read_commerce_state(
        store_id=STORE, product_id="123", variant_id="456"
    )

    assert result.failure is ShopifyTransportFailure.TIMEOUT
    assert len(opener.calls) == 1


def test_commerce_read_uses_single_variant_resource_path() -> None:
    opener = Opener(Response(b'{"variant": {"id": 456}}'))

    result = transport(opener).read_commerce_state(
        store_id=STORE, product_id="123", variant_id="456"
    )

    assert result.failure is None
    assert len(opener.calls) == 1
    request, _timeout = opener.calls[0]
    parsed = urlsplit(request.full_url)
    assert parsed.path == "/admin/api/2026-07/variants/456.json"
    assert parse_qs(parsed.query)["fields"] == [
        "id,product_id,title,price,inventory_quantity,inventory_policy,available_for_sale"
    ]


@pytest.mark.parametrize("body", [b"not-json", b"\xff", b"[]"])
def test_malformed_body_is_classified_without_retaining_body(body: bytes) -> None:
    result = transport(Opener(Response(body))).read_product(
        store_id=STORE, product_id="123"
    )

    assert result.failure is ShopifyTransportFailure.MALFORMED_RESPONSE
    assert result.http_status == 200
    assert result.payload is None
    assert body.decode("utf-8", errors="replace") not in repr(result)


def test_invalid_store_is_rejected_before_credentials_or_network() -> None:
    opener = Opener(Response(b"{}"))
    provider = TokenProvider()

    result = transport(opener, token_provider=provider).read_product(
        store_id="foreign.example.com", product_id="123"
    )

    assert result.failure is ShopifyTransportFailure.NETWORK_ERROR
    assert provider.calls == 0
    assert opener.calls == []


def test_credential_failure_is_redacted_and_makes_no_network_call() -> None:
    opener = Opener(Response(b"{}"))

    class InvalidProvider:
        def get_access_token(self) -> str:
            raise ShopifyCredentialError("Shopify access token is unavailable")

    result = transport(opener, token_provider=InvalidProvider()).read_product(
        store_id=STORE, product_id="123"
    )

    assert result.failure is ShopifyTransportFailure.UNAUTHORIZED
    assert opener.calls == []
    assert "shpat_" not in repr(result)


def test_keychain_provider_rejects_missing_or_wrongly_shaped_value() -> None:
    def runner(argv: list[str], **kwargs: object) -> CompletedProcess[str]:
        return CompletedProcess(argv, 1, stdout="", stderr="private keychain error")

    provider = MacOSKeychainAccessTokenProvider(
        service="service",
        account="account",
        runner=runner,
    )

    with pytest.raises(ShopifyCredentialError, match="unavailable") as error:
        provider.get_access_token()

    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "kwargs",
    [{"timeout_seconds": 0}, {"timeout_seconds": -1}, {"api_version": "latest"}],
)
def test_transport_rejects_unbounded_or_implicit_configuration(
    kwargs: Mapping[str, object],
) -> None:
    with pytest.raises(ValueError):
        UrllibShopifyReadTransport(token_provider=TokenProvider(), **kwargs)
