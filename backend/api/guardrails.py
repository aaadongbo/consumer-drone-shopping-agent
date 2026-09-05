"""Transport wiring for the S11 security guardrails."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.runtime.guardrails import safe_error_body


def install_cors_guardrail(api: FastAPI, origins: Iterable[str]) -> None:
    """Install exact-origin CORS without wildcard or credential reflection."""

    configured = tuple(origins)
    if not configured or any(origin == "*" or "*" in origin for origin in configured):
        raise ValueError("explicit CORS origins are required")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type"],
    )


def install_safe_exception_handler(api: FastAPI) -> None:
    """Map unexpected exceptions to a stable body without diagnostics."""

    @api.exception_handler(Exception)
    async def handle_unexpected(_request: Request, _error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=safe_error_body("INTERNAL_ERROR"),
        )


__all__ = ["install_cors_guardrail", "install_safe_exception_handler"]
