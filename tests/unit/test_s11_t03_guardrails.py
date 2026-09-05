"""Unit coverage for the S11 in-process release guardrails."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.runtime import (
    ConcurrencyLimitExceeded,
    InProcessConcurrencyLimiter,
    InProcessRateLimiter,
    IntentAdapterMode,
    RateLimitExceeded,
    ReadOnlyOperationLedger,
    ReleaseConfig,
    ReleaseEnvironment,
    build_health_report,
    is_allowed_origin,
    redact_for_log,
    safe_error_body,
)

pytestmark = pytest.mark.unit


def _config() -> ReleaseConfig:
    return ReleaseConfig(
        release_mode="closed_beta",
        environment=ReleaseEnvironment.STAGING,
        hosting_runtime="single_container",
        store_id="shopify-store:pilot",
        shopify_adapter_mode="pilot_read_only",
        credential_ref="secret://shopify-read-only",
        secret_store_ref="secret-store://pilot",
        widget_origins=("https://staging.example.test",),
        intent_adapter_mode=IntentAdapterMode.DETERMINISTIC,
        pilot_readiness_ref="staging://pilot-readiness",
        corpus_manifest_ref="staging://corpus-manifest",
    )


def test_health_report_is_safe_and_fails_closed_on_readiness() -> None:
    report = build_health_report(
        _config(),
        readiness_ok=False,
        dependency_checks={"shopify": True, "corpus": False},
        clock=lambda: datetime(2026, 9, 5, tzinfo=UTC),
    )

    assert report.status == "not_ready"
    assert report.to_safe_dict() == {
        "status": "not_ready",
        "checks": {
            "process": "ok",
            "configuration": "ok",
            "pilot_readiness": "not_ready",
            "dependency:shopify": "ok",
            "dependency:corpus": "not_ready",
        },
        "generated_at": "2026-09-05T00:00:00+00:00",
    }
    assert "credential" not in repr(report.to_safe_dict()).lower()


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("https://staging.example.test", True),
        ("https://staging.example.test/", True),
        ("https://evil.example.test", False),
        ("*", False),
        ("https://*.example.test", False),
        ("not-an-origin", False),
    ],
)
def test_origin_policy_requires_exact_explicit_origin(
    origin: str, expected: bool
) -> None:
    assert is_allowed_origin(origin, ("https://staging.example.test",)) is expected


def test_rate_limiter_returns_stable_retry_boundary() -> None:
    now = [100.0]
    limiter = InProcessRateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    limiter.allow("session-1")
    limiter.allow("session-1")
    with pytest.raises(RateLimitExceeded) as error:
        limiter.allow("session-1")
    assert error.value.retry_after_seconds == 60
    now[0] = 160.0
    limiter.allow("session-1")


def test_concurrency_limiter_enforces_session_and_global_bounds() -> None:
    limiter = InProcessConcurrencyLimiter(global_limit=2, session_limit=1)
    with limiter.acquire("session-1"):
        with pytest.raises(ConcurrencyLimitExceeded):
            with limiter.acquire("session-1"):
                pass
        with limiter.acquire("session-2"):
            with pytest.raises(ConcurrencyLimitExceeded):
                with limiter.acquire("session-3"):
                    pass


def test_redaction_omits_payloads_and_secret_material() -> None:
    safe = redact_for_log(
        {
            "correlation_id": "c-1",
            "authorization": "Bearer secret",
            "nested": {"access_token": "token", "source_text": "official text"},
            "count": 2,
        }
    )
    assert safe == {
        "correlation_id": "c-1",
        "authorization": "[REDACTED]",
        "nested": {"access_token": "[REDACTED]", "source_text": "[OMITTED]"},
        "count": 2,
    }


def test_read_only_ledger_has_no_write_surface() -> None:
    ledger = ReadOnlyOperationLedger(allowed_operations=frozenset({"read_product"}))
    ledger.record_read("read_product")
    assert ledger.read_count == 1
    assert ledger.write_call_count == 0
    assert ledger.operations == ("read_product",)
    assert not hasattr(ledger, "record_write")
    with pytest.raises(Exception, match="read-allowlisted"):
        ledger.record_read("write_product")


def test_safe_error_body_excludes_internal_diagnostics() -> None:
    body = safe_error_body("internal_exception", retryable=True)
    assert body == {
        "error_code": "INTERNAL_EXCEPTION",
        "message": "The request could not be completed.",
        "retryable": True,
    }
    assert "traceback" not in repr(body).lower()
