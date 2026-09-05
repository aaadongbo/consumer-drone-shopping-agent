"""Fail-closed, internal release configuration for the S11 closed beta.

This module deliberately contains no credentials and does not change the public
Conversation wire contract.  Environment values are validated before a runtime
composition is built; secret material is injected by an adapter outside this
configuration object.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReleaseConfigError(ValueError):
    """Safe configuration failure with no credential or payload details."""


class ReleaseEnvironment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    BETA = "beta"


class IntentAdapterMode(StrEnum):
    DETERMINISTIC = "deterministic"
    PROVIDER = "provider"


class ReleaseConfig(BaseModel):
    """Validated internal settings required before serving closed-beta traffic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    release_mode: Literal["closed_beta"]
    environment: ReleaseEnvironment
    hosting_runtime: Literal["single_container"]
    store_id: str = Field(min_length=1)
    shopify_adapter_mode: Literal["pilot_read_only"]
    credential_ref: str = Field(min_length=1)
    secret_store_ref: str | None = None
    keychain_service: str | None = None
    widget_origins: tuple[str, ...] = Field(min_length=1)
    intent_adapter_mode: IntentAdapterMode
    model_provider: str | None = None
    model_id: str | None = None
    pilot_readiness_ref: str = Field(min_length=1)
    corpus_manifest_ref: str = Field(min_length=1)

    request_timeout_ms: int = Field(default=12_000, ge=1, le=12_000)
    health_timeout_ms: int = Field(default=1_500, ge=1, le=1_500)
    shopify_request_timeout_ms: int = Field(default=5_000, ge=1, le=5_000)
    max_shopify_read_calls_per_turn: int = Field(default=2, ge=1, le=2)
    max_action_rounds: int = Field(default=2, ge=1, le=2)
    max_tool_calls_per_turn: int = Field(default=2, ge=1, le=2)
    max_model_tokens_per_turn: int = Field(default=1_200, ge=1, le=1_200)
    max_response_tokens: int = Field(default=900, ge=1, le=900)
    max_concurrent_turns_global: int = Field(default=4, ge=1, le=4)
    max_concurrent_turns_per_session: int = Field(default=1, ge=1, le=1)
    rate_limit_per_session_per_minute: int = Field(default=6, ge=1, le=6)
    rate_limit_per_store_per_minute: int = Field(default=30, ge=1, le=30)
    log_redaction_required: Literal[True] = True
    log_retention_days: int = Field(default=7, ge=1, le=7)
    deployment_rollback_window_minutes: int = Field(default=30, ge=1, le=30)

    @model_validator(mode="after")
    def validate_release_boundary(self) -> ReleaseConfig:
        if not self.store_id.strip():
            raise ReleaseConfigError("store scope is required")
        if not _is_credential_ref(self.credential_ref):
            raise ReleaseConfigError("credential reference is invalid")
        if self.environment is ReleaseEnvironment.LOCAL:
            if not self.keychain_service or not self.keychain_service.strip():
                raise ReleaseConfigError("local keychain reference is required")
            if self.secret_store_ref is not None:
                raise ReleaseConfigError("local runtime cannot use hosted secret store")
            if not self.credential_ref.startswith("keychain://"):
                raise ReleaseConfigError("local runtime requires keychain credentials")
        else:
            if not self.secret_store_ref or not self.secret_store_ref.strip():
                raise ReleaseConfigError("hosted secret store reference is required")
            if self.keychain_service is not None:
                raise ReleaseConfigError("hosted runtime cannot use local keychain")
            if not self.credential_ref.startswith("secret://"):
                raise ReleaseConfigError("hosted runtime requires secret references")
        if self.intent_adapter_mode is IntentAdapterMode.PROVIDER:
            if not self.model_provider or not self.model_provider.strip():
                raise ReleaseConfigError("model provider is required")
            if not self.model_id or not self.model_id.strip():
                raise ReleaseConfigError("model id is required")
        elif self.model_provider is not None or self.model_id is not None:
            raise ReleaseConfigError("deterministic mode cannot configure a live model")
        if self.shopify_adapter_mode != "pilot_read_only":
            raise ReleaseConfigError("only read-only pilot adapter is supported")
        if any(not _is_explicit_origin(origin) for origin in self.widget_origins):
            raise ReleaseConfigError("widget origins must be explicit http(s) origins")
        return self

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ReleaseConfig:
        """Build settings from a narrow, explicit environment allowlist."""

        source = os.environ if environ is None else environ

        def required(name: str) -> str:
            value = source.get(name)
            if value is None or not value.strip():
                raise ReleaseConfigError("required release configuration is missing")
            return value.strip()

        def optional(name: str) -> str | None:
            value = source.get(name)
            return value.strip() if value and value.strip() else None

        def integer(name: str, default: int) -> int:
            value = optional(name)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError as error:
                raise ReleaseConfigError("release budget is invalid") from error

        origins = tuple(
            origin.strip()
            for origin in required("DRONE_WIDGET_ORIGINS").split(",")
            if origin.strip()
        )
        return cls(
            release_mode=required("DRONE_RELEASE_MODE"),
            environment=required("DRONE_ENVIRONMENT"),
            hosting_runtime=required("DRONE_HOSTING_RUNTIME"),
            store_id=required("DRONE_STORE_ID"),
            shopify_adapter_mode=required("DRONE_SHOPIFY_ADAPTER_MODE"),
            credential_ref=required("DRONE_CREDENTIAL_REF"),
            secret_store_ref=optional("DRONE_SECRET_STORE_REF"),
            keychain_service=optional("DRONE_KEYCHAIN_SERVICE"),
            widget_origins=origins,
            intent_adapter_mode=required("DRONE_INTENT_ADAPTER_MODE"),
            model_provider=optional("DRONE_MODEL_PROVIDER"),
            model_id=optional("DRONE_MODEL_ID"),
            pilot_readiness_ref=required("DRONE_PILOT_READINESS_REF"),
            corpus_manifest_ref=required("DRONE_CORPUS_MANIFEST_REF"),
            request_timeout_ms=integer("DRONE_REQUEST_TIMEOUT_MS", 12_000),
            health_timeout_ms=integer("DRONE_HEALTH_TIMEOUT_MS", 1_500),
            shopify_request_timeout_ms=integer(
                "DRONE_SHOPIFY_REQUEST_TIMEOUT_MS", 5_000
            ),
            max_shopify_read_calls_per_turn=integer("DRONE_MAX_SHOPIFY_READ_CALLS", 2),
            max_action_rounds=integer("DRONE_MAX_ACTION_ROUNDS", 2),
            max_tool_calls_per_turn=integer("DRONE_MAX_TOOL_CALLS", 2),
            max_model_tokens_per_turn=integer("DRONE_MAX_MODEL_TOKENS", 1_200),
            max_response_tokens=integer("DRONE_MAX_RESPONSE_TOKENS", 900),
            max_concurrent_turns_global=integer("DRONE_MAX_GLOBAL_CONCURRENCY", 4),
            max_concurrent_turns_per_session=integer(
                "DRONE_MAX_SESSION_CONCURRENCY", 1
            ),
            rate_limit_per_session_per_minute=integer("DRONE_SESSION_RATE_LIMIT", 6),
            rate_limit_per_store_per_minute=integer("DRONE_STORE_RATE_LIMIT", 30),
            log_redaction_required=True,
            log_retention_days=integer("DRONE_LOG_RETENTION_DAYS", 7),
            deployment_rollback_window_minutes=integer(
                "DRONE_ROLLBACK_WINDOW_MINUTES", 30
            ),
        )

    def safe_metadata(self) -> dict[str, object]:
        """Return diagnostics without credential references or secret values."""

        data = self.model_dump(mode="json")
        data.pop("credential_ref", None)
        data.pop("secret_store_ref", None)
        data.pop("keychain_service", None)
        data["credential_configured"] = True
        return data


def _is_credential_ref(value: str) -> bool:
    for prefix in ("keychain://", "secret://"):
        if value.startswith(prefix):
            return len(value) > len(prefix)
    return False


def _is_explicit_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.path.rstrip("/")
        and not parsed.query
        and not parsed.fragment
        and "*" not in value
    )


__all__ = [
    "IntentAdapterMode",
    "ReleaseConfig",
    "ReleaseConfigError",
    "ReleaseEnvironment",
]
