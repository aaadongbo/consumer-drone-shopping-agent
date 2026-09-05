"""Integration checks for S11 CORS and safe exception transport behavior."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import install_cors_guardrail, install_safe_exception_handler

pytestmark = pytest.mark.integration


def _app() -> FastAPI:
    app = FastAPI()
    install_cors_guardrail(app, ("https://staging.example.test",))
    install_safe_exception_handler(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret token and stack must not escape")

    return app


def test_cors_allows_configured_origin_and_rejects_unapproved_origin() -> None:
    client = TestClient(_app())
    allowed = client.options(
        "/health",
        headers={
            "Origin": "https://staging.example.test",
            "Access-Control-Request-Method": "GET",
        },
    )
    rejected = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "https://staging.example.test"
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_unexpected_error_is_safe_and_contains_no_diagnostics() -> None:
    response = TestClient(_app(), raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "INTERNAL_ERROR",
        "message": "The request could not be completed.",
        "retryable": False,
    }
    assert "secret" not in response.text.lower()
    assert "traceback" not in response.text.lower()
