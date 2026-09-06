"""S11-T06 ASGI entrypoint readiness and fail-closed transport checks."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.shopify import ShopifyCredentialError
from scripts.s11_runtime_entrypoint import (
    APPROVED_ORIGIN,
    _EnvironmentAccessTokenProvider,
    create_runtime_app,
)

pytestmark = pytest.mark.unit


def test_runtime_entrypoint_is_live_but_not_ready_without_configuration() -> None:
    client = TestClient(create_runtime_app({}), raise_server_exceptions=False)

    health = client.get("/healthz")
    ready = client.get("/readyz")
    turn = client.post("/v1/conversation/turn", json={})

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["credential_values_exposed"] is False
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert turn.status_code == 503
    assert turn.json() == {
        "error_code": "RUNTIME_NOT_READY",
        "message": "The conversation service is not ready.",
        "retryable": False,
    }
    assert "secret" not in turn.text.lower()


def test_runtime_entrypoint_keeps_exact_cors_and_never_wildcards() -> None:
    client = TestClient(create_runtime_app({}), raise_server_exceptions=False)

    allowed = client.options(
        "/healthz",
        headers={
            "Origin": APPROVED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    rejected = client.options(
        "/healthz",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == APPROVED_ORIGIN
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_client_credentials_token_does_not_require_legacy_shpat_prefix() -> None:
    provider = _EnvironmentAccessTokenProvider(
        {"DRONE_SHOPIFY_ACCESS_TOKEN": "opaque-client-credentials-token"}
    )

    assert provider.get_access_token() == "opaque-client-credentials-token"


def test_client_credentials_token_rejects_blank_or_whitespace_values() -> None:
    for value in ("", "   ", "opaque\ttoken"):
        provider = _EnvironmentAccessTokenProvider(
            {"DRONE_SHOPIFY_ACCESS_TOKEN": value}
        )

        with pytest.raises(ShopifyCredentialError, match="unavailable"):
            provider.get_access_token()
