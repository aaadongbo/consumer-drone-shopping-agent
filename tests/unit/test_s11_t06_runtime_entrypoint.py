"""S11-T06 ASGI entrypoint readiness and fail-closed transport checks."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from backend.shopify import ShopifyCredentialError, ShopifyTransportResult
from scripts import s11_runtime_entrypoint
from scripts.s11_runtime_entrypoint import (
    APPROVED_ORIGIN,
    APPROVED_SHOPIFY_STORE_DOMAIN,
    APPROVED_STORE_ID,
    RuntimeDependencyError,
    _CanonicalStoreTransport,
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


def test_slow_dependency_initialization_does_not_block_liveness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_dependencies(*_args: object, **_kwargs: object) -> object:
        started.set()
        assert release.wait(timeout=1)
        raise s11_runtime_entrypoint.RuntimeDependencyError("not ready")

    monkeypatch.setattr(
        s11_runtime_entrypoint,
        "_build_dependencies",
        slow_dependencies,
    )
    app = create_runtime_app(
        {
            "DRONE_RELEASE_MODE": "closed_beta",
            "DRONE_ENVIRONMENT": "staging",
            "DRONE_HOSTING_RUNTIME": "single_container",
            "DRONE_STORE_ID": "shopify-store:bys-user-store-578412-7a11gk0u",
            "DRONE_SHOPIFY_ADAPTER_MODE": "pilot_read_only",
            "DRONE_CREDENTIAL_REF": "secret://shopify-read-only",
            "DRONE_SECRET_STORE_REF": "render://consumer-drone-agent-staging",
            "DRONE_WIDGET_ORIGINS": APPROVED_ORIGIN,
            "DRONE_INTENT_ADAPTER_MODE": "deterministic",
            "DRONE_PILOT_READINESS_REF": "pilot",
            "DRONE_CORPUS_MANIFEST_REF": "corpus",
        }
    )
    try:
        assert started.wait(timeout=0.2)
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503
        assert client.post("/v1/conversation/turn", json={}).status_code == 503
    finally:
        release.set()


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


class _RecordingShopifyTransport:
    def __init__(self) -> None:
        self.store_ids: list[str] = []

    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        self.store_ids.append(store_id)
        return ShopifyTransportResult(payload={})

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        self.store_ids.append(store_id)
        return ShopifyTransportResult(payload={})

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        self.store_ids.append(store_id)
        return ShopifyTransportResult(payload={})


def test_canonical_store_scope_maps_only_to_approved_shopify_domain() -> None:
    delegate = _RecordingShopifyTransport()
    transport = _CanonicalStoreTransport(
        delegate,
        canonical_store_id=APPROVED_STORE_ID,
        shopify_store_domain=APPROVED_SHOPIFY_STORE_DOMAIN,
    )

    transport.read_product(store_id=APPROVED_STORE_ID, product_id="9278439686282")

    assert delegate.store_ids == [APPROVED_SHOPIFY_STORE_DOMAIN]
    with pytest.raises(RuntimeDependencyError, match="outside the pilot scope"):
        transport.read_product(store_id="other-store", product_id="9278439686282")
