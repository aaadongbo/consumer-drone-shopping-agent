"""S11-T06 unit checks for release, CI, smoke, and rollback metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.s11_release_boundary import (
    APPROVED_ORIGIN,
    EXPECTED_STAGING_URL,
    REQUIRED_CHECKS,
    ReleaseBoundaryError,
    redact_smoke_metadata,
    validate_release_candidate,
    validate_rollback_plan,
    validate_smoke_plan,
)

pytestmark = pytest.mark.unit

CONFIG_PATH = Path("deploy/render_staging_release.json")


def _config(**overrides: object) -> dict[str, object]:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data.update(overrides)
    return data


def test_release_candidate_binds_render_origin_checks_and_identity() -> None:
    result = validate_release_candidate(_config())

    assert result.accepted is True
    assert result.metadata["staging_url"] == EXPECTED_STAGING_URL
    assert result.metadata["allowed_cors_origins"] == [APPROVED_ORIGIN]
    assert result.metadata["required_checks"] == list(REQUIRED_CHECKS)
    assert "0123456789abcdef0123456789abcdef01234567" in result.metadata["image_tag"]
    assert "token" not in json.dumps(result.to_dict()).lower()


@pytest.mark.parametrize(
    "override",
    [
        {"hosting_vendor": "Fly.io"},
        {"plan": "free"},
        {"kubernetes": True},
        {"multi_region": True},
        {"staging_url": "https://different.example"},
        {"allowed_cors_origins": ["*"]},
        {"required_checks": ["quality / unit"]},
        {"git_sha": "short"},
        {"image_tag": "latest"},
        {"write_capable_credentials": True},
        {"external_model_calls": True},
        {"database_migration": True},
        {"storefront_password_protected": False},
    ],
)
def test_release_candidate_fails_closed_on_unapproved_boundaries(
    override: dict[str, object],
) -> None:
    with pytest.raises(ReleaseBoundaryError):
        validate_release_candidate(_config(**override))


def test_smoke_plan_enforces_three_product_zero_write_budget() -> None:
    smoke = _config()["smoke_plan"]
    result = validate_smoke_plan(smoke)

    assert result.metadata["products"] == [
        ["Mini3", "9278439686282", "50107364802698"],
        ["Air3", "9278460821642", "50107426603146"],
        ["Mavic3", "9278439719050", "50107364901002"],
    ]
    assert result.metadata["shopify_writes"] == 0
    assert result.metadata["max_shopify_reads_total"] == 18


@pytest.mark.parametrize(
    "override",
    [
        {"max_http_requests": 21},
        {"max_conversation_turns": 13},
        {"max_shopify_reads_per_turn": 3},
        {"max_shopify_reads_total": 19},
        {"shopify_writes": 1},
        {"retry_count": 1},
        {"external_model_calls": True},
        {"intent_adapter": "provider"},
        {"products": [["Mini3", "9278439686282", "wrong"]]},
        {"metadata_fields": ["raw_response"]},
    ],
)
def test_smoke_plan_rejects_budget_and_data_boundary_drift(
    override: dict[str, object],
) -> None:
    smoke = dict(_config()["smoke_plan"])
    smoke.update(override)

    with pytest.raises(ReleaseBoundaryError):
        validate_smoke_plan(smoke)


def test_rollback_plan_requires_previous_immutable_identity_and_operator() -> None:
    plan = _config()["rollback_plan"]
    result = validate_rollback_plan(
        plan,
        git_sha="0123456789abcdef0123456789abcdef01234567",
    )

    assert result.metadata["operator"] == "russeell"
    assert result.metadata["window_minutes"] == 30
    assert result.metadata["database_migration"] is False


def test_rollback_plan_rejects_same_version_or_destructive_operation() -> None:
    plan = dict(_config()["rollback_plan"])
    plan["previous_known_good_git_sha"] = "0123456789abcdef0123456789abcdef01234567"

    with pytest.raises(ReleaseBoundaryError):
        validate_rollback_plan(
            plan,
            git_sha="0123456789abcdef0123456789abcdef01234567",
        )

    plan = dict(_config()["rollback_plan"])
    plan["destructive_data_operation"] = True
    with pytest.raises(ReleaseBoundaryError):
        validate_rollback_plan(
            plan,
            git_sha="0123456789abcdef0123456789abcdef01234567",
        )


def test_redacted_smoke_metadata_rejects_raw_payload_like_fields() -> None:
    result = redact_smoke_metadata(
        {
            "status": "pass",
            "correlation_id": "corr-123",
            "latency_ms": 25,
            "shopify_write_count": 0,
            "checksum": "abc",
        }
    )
    assert result.accepted is True

    with pytest.raises(ReleaseBoundaryError):
        redact_smoke_metadata({"raw_response": "not allowed", "shopify_write_count": 0})
