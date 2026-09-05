"""Small, in-process guardrails for the closed-beta runtime boundary.

The module intentionally owns policy, not transport or persistence.  It keeps
health data, counters, rate windows, and concurrency state in memory and never
stores request payloads or credential material.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from backend.runtime.config import ReleaseConfig

SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "credential",
    "header",
    "password",
    "payload",
    "raw_response",
    "secret",
    "token",
)


class GuardrailError(RuntimeError):
    """Safe, stable error for an internal guardrail rejection."""


class RateLimitExceeded(GuardrailError):
    """The configured in-process request window is exhausted."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class ConcurrencyLimitExceeded(GuardrailError):
    """A global or per-session in-process concurrency bound was reached."""


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Metadata-only health result safe to expose to an operator."""

    status: str
    checks: Mapping[str, str]
    generated_at: datetime

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": dict(self.checks),
            "generated_at": self.generated_at.isoformat(),
        }


def build_health_report(
    config: ReleaseConfig,
    *,
    readiness_ok: bool,
    dependency_checks: Mapping[str, bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> HealthReport:
    """Build a bounded liveness/readiness report with no payloads or secrets."""

    checks: dict[str, str] = {
        "process": "ok",
        "configuration": "ok",
        "pilot_readiness": "ok" if readiness_ok else "not_ready",
    }
    for name, passed in (dependency_checks or {}).items():
        checks[f"dependency:{name}"] = "ok" if passed else "not_ready"
    status = "ok" if all(value == "ok" for value in checks.values()) else "not_ready"
    now = (clock or (lambda: datetime.now(UTC)))()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    # Accessing this value documents the hard bound without creating a timer or
    # a background worker; the function itself is intentionally deterministic.
    _ = config.health_timeout_ms
    return HealthReport(status=status, checks=checks, generated_at=now)


def is_allowed_origin(origin: str | None, configured_origins: tuple[str, ...]) -> bool:
    """Accept only exact, explicit origins; wildcard and malformed values fail."""

    if not origin or origin == "*" or "*" in origin:
        return False
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path.rstrip("/")
        or parsed.query
        or parsed.fragment
    ):
        return False
    return origin.rstrip("/") in {item.rstrip("/") for item in configured_origins}


def safe_error_body(error_code: str, *, retryable: bool = False) -> dict[str, object]:
    """Return a stable public error shape without diagnostics or exception text."""

    safe_code = "".join(ch for ch in error_code.upper() if ch.isalnum() or ch == "_")
    return {
        "error_code": safe_code or "INTERNAL_ERROR",
        "message": "The request could not be completed.",
        "retryable": retryable,
    }


def redact_for_log(value: Any) -> Any:
    """Recursively retain safe metadata while replacing sensitive fields."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(
                fragment in key_text.lower() for fragment in SENSITIVE_KEY_FRAGMENTS
            ):
                result[key_text] = "[REDACTED]"
            elif key_text.lower() in {"user_text", "raw", "source_text"}:
                result[key_text] = "[OMITTED]"
            else:
                result[key_text] = redact_for_log(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_for_log(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return "[OMITTED]"


@dataclass(slots=True)
class ReadOnlyOperationLedger:
    """Metadata-only counter with no write-capable method or payload storage."""

    allowed_operations: frozenset[str]
    _reads: list[str] = field(default_factory=list, init=False, repr=False)

    def record_read(self, operation: str) -> None:
        if operation not in self.allowed_operations:
            raise GuardrailError("operation is not read-allowlisted")
        self._reads.append(operation)

    @property
    def read_count(self) -> int:
        return len(self._reads)

    @property
    def write_call_count(self) -> int:
        return 0

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(self._reads)


class InProcessRateLimiter:
    """Fixed-window limiter suitable only for one process and closed beta."""

    def __init__(
        self, *, limit: int, window_seconds: int = 60, clock=monotonic
    ) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("rate limit values must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= self._window_seconds:
                events.popleft()
            if len(events) >= self._limit:
                retry_after = max(1, int(self._window_seconds - (now - events[0])))
                raise RateLimitExceeded(retry_after)
            events.append(now)


class InProcessConcurrencyLimiter:
    """Bounded process-local concurrency with global and session limits."""

    def __init__(self, *, global_limit: int, session_limit: int) -> None:
        if global_limit <= 0 or session_limit <= 0:
            raise ValueError("concurrency limits must be positive")
        self._global_limit = global_limit
        self._session_limit = session_limit
        self._global_active = 0
        self._session_active: dict[str, int] = {}
        self._lock = Lock()

    @contextmanager
    def acquire(self, session_id: str) -> Iterator[None]:
        with self._lock:
            active = self._session_active.get(session_id, 0)
            if (
                self._global_active >= self._global_limit
                or active >= self._session_limit
            ):
                raise ConcurrencyLimitExceeded("concurrency limit exceeded")
            self._global_active += 1
            self._session_active[session_id] = active + 1
        try:
            yield
        finally:
            with self._lock:
                self._global_active -= 1
                remaining = self._session_active[session_id] - 1
                if remaining:
                    self._session_active[session_id] = remaining
                else:
                    self._session_active.pop(session_id, None)


__all__ = [
    "ConcurrencyLimitExceeded",
    "GuardrailError",
    "HealthReport",
    "InProcessConcurrencyLimiter",
    "InProcessRateLimiter",
    "RateLimitExceeded",
    "ReadOnlyOperationLedger",
    "build_health_report",
    "is_allowed_origin",
    "redact_for_log",
    "safe_error_body",
]
