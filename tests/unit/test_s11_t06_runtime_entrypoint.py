"""S11-T06 ASGI entrypoint readiness and fail-closed transport checks."""

from __future__ import annotations

from fastapi.testclient import TestClient

from scripts.s11_runtime_entrypoint import APPROVED_ORIGIN, create_runtime_app


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
