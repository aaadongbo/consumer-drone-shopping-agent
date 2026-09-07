"""Injected, read-only Shopify transport for the Slice 10 pilot."""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)


class ShopifyTransportFailure(StrEnum):
    """Safe failure classes without response bodies or credential details."""

    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_FOUND = "NOT_FOUND"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    NETWORK_ERROR = "NETWORK_ERROR"


@dataclass(frozen=True, slots=True)
class ShopifyTransportResult:
    """In-memory response envelope; payload is never retained by a ledger."""

    payload: Mapping[str, Any] | None = field(default=None, repr=False)
    http_status: int | None = None
    failure: ShopifyTransportFailure | None = None


class ShopifyReadTransport(Protocol):
    """The three explicit Shopify reads required by the adapter."""

    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        """Read one explicitly addressed Product and its Variant references."""
        ...

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        """Read Variants owned by one explicitly addressed Product."""
        ...

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        """Read current commerce fields for one explicit Variant."""
        ...


class ShopifyTokenProvider(Protocol):
    """Minimal credential boundary; implementations never expose the token."""

    def get_access_token(self) -> str: ...


class ShopifyCredentialError(RuntimeError):
    """Credential lookup failed without exposing the lookup value."""


class MacOSKeychainAccessTokenProvider:
    """Read one Shopify access token from an exact macOS Keychain item."""

    def __init__(
        self,
        *,
        service: str,
        account: str,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self._service = service
        self._account = account
        self._runner = runner or subprocess.run

    def get_access_token(self) -> str:
        """Return the token in process memory, or a redacted credential error."""
        try:
            result = self._runner(
                [
                    "/usr/bin/security",
                    "find-generic-password",
                    "-s",
                    self._service,
                    "-a",
                    self._account,
                    "-w",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ShopifyCredentialError(
                "Shopify access token is unavailable"
            ) from error
        value = (
            result.stdout.rstrip("\r\n")
            if result.returncode == 0 and isinstance(result.stdout, str)
            else ""
        )
        if not value.startswith("shpat_"):
            raise ShopifyCredentialError("Shopify access token is unavailable")
        return value


class _NoRedirectHandler(HTTPRedirectHandler):
    def http_error_301(self, req, fp, code, msg, headers):  # type: ignore[no-untyped-def]
        raise HTTPError(req.full_url, code, "redirect refused", headers, fp)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


_STORE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


class UrllibShopifyReadTransport:
    """Small no-retry HTTPS transport with only typed read entry points."""

    def __init__(
        self,
        *,
        token_provider: ShopifyTokenProvider,
        api_version: str = "2026-07",
        timeout_seconds: float = 5.0,
        proxy_url: str | None = None,
        ca_bundle: str | None = None,
        opener: Any | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Shopify timeout must be positive")
        if re.fullmatch(r"\d{4}-\d{2}", api_version) is None:
            raise ValueError("Shopify API version must use YYYY-MM format")
        self._token_provider = token_provider
        self._api_version = api_version
        self._timeout_seconds = timeout_seconds
        self._opener = opener or self._build_opener(
            proxy_url=proxy_url,
            ca_bundle=ca_bundle,
        )

    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        product_id = _path_id(product_id)
        query = urlencode(
            {"fields": "id,title,status,published_at,variants"},
        )
        return self._read_json(
            store_id=store_id,
            path=f"/products/{product_id}.json?{query}",
        )

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        product_id = _path_id(product_id)
        query = urlencode(
            {"fields": "id,product_id,title,option1,option2,option3"},
        )
        return self._read_json(
            store_id=store_id,
            path=f"/products/{product_id}/variants.json?{query}",
        )

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        variant_id = _path_id(variant_id)
        query = urlencode(
            {
                "fields": (
                    "id,product_id,title,price,inventory_quantity,"
                    "inventory_policy,available_for_sale"
                )
            },
        )
        return self._read_json(
            store_id=store_id,
            # Shopify's single-Variant REST resource is addressed by Variant
            # ID directly.  The product-scoped collection endpoint is only
            # for listing variants and can return NOT_FOUND for a valid
            # Variant when used as a single-resource read.
            path=f"/variants/{variant_id}.json?{query}",
        )

    def _read_json(self, *, store_id: str, path: str) -> ShopifyTransportResult:
        if not _STORE_RE.fullmatch(store_id):
            return ShopifyTransportResult(failure=ShopifyTransportFailure.NETWORK_ERROR)
        try:
            token = self._token_provider.get_access_token()
        except ShopifyCredentialError:
            return ShopifyTransportResult(
                failure=ShopifyTransportFailure.UNAUTHORIZED,
            )

        request = Request(
            f"https://{store_id}/admin/api/{self._api_version}{path}",
            headers={
                "Accept": "application/json",
                "X-Shopify-Access-Token": token,
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                body = response.read()
                status = int(response.status)
        except HTTPError as error:
            return ShopifyTransportResult(
                http_status=int(error.code),
                failure=_failure_for_http_status(int(error.code)),
            )
        except (URLError, TimeoutError, OSError) as error:
            return ShopifyTransportResult(failure=_failure_for_exception(error))

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ShopifyTransportResult(
                http_status=status,
                failure=ShopifyTransportFailure.MALFORMED_RESPONSE,
            )
        if not isinstance(payload, dict):
            return ShopifyTransportResult(
                http_status=status,
                failure=ShopifyTransportFailure.MALFORMED_RESPONSE,
            )
        return ShopifyTransportResult(payload=payload, http_status=status)

    @staticmethod
    def _build_opener(*, proxy_url: str | None, ca_bundle: str | None):
        selected_ca_bundle = ca_bundle or os.environ.get("SSL_CERT_FILE")
        if selected_ca_bundle is not None and Path(selected_ca_bundle).is_file():
            context = ssl.create_default_context(cafile=selected_ca_bundle)
        else:
            context = ssl.create_default_context()
        handlers: list[Any] = [_NoRedirectHandler()]
        if proxy_url is not None:
            handlers.append(ProxyHandler({"http": proxy_url, "https": proxy_url}))
        handlers.append(HTTPSHandler(context=context))
        return build_opener(*handlers)


def _failure_for_http_status(status: int) -> ShopifyTransportFailure:
    if status == 429:
        return ShopifyTransportFailure.RATE_LIMITED
    if status in {401, 403}:
        return ShopifyTransportFailure.UNAUTHORIZED
    if status == 404:
        return ShopifyTransportFailure.NOT_FOUND
    if status in {408, 504}:
        return ShopifyTransportFailure.TIMEOUT
    return ShopifyTransportFailure.NETWORK_ERROR


def _failure_for_exception(error: BaseException) -> ShopifyTransportFailure:
    reason = str(getattr(error, "reason", error)).lower()
    if "timeout" in reason or "timed out" in reason:
        return ShopifyTransportFailure.TIMEOUT
    return ShopifyTransportFailure.NETWORK_ERROR


def _path_id(value: str) -> str:
    """Accept only numeric Shopify IDs before interpolating an endpoint path."""
    if value.isdigit():
        return value
    for prefix in (
        "gid://shopify/Product/",
        "gid://shopify/Variant/",
        "gid://shopify/ProductVariant/",
    ):
        candidate = value.removeprefix(prefix)
        if candidate.isdigit():
            return candidate
    raise ValueError("Shopify resource ID must be numeric")


__all__ = [
    "MacOSKeychainAccessTokenProvider",
    "ShopifyCredentialError",
    "ShopifyReadTransport",
    "ShopifyTokenProvider",
    "ShopifyTransportFailure",
    "ShopifyTransportResult",
    "UrllibShopifyReadTransport",
]
