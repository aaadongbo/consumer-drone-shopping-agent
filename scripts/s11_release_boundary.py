"""S11 release-boundary validation for CI, staging, smoke, and rollback.

The module stores only metadata and policy decisions. It never reads
credentials, never contacts Render or Shopify, and fails closed when a caller
tries to represent a live action without immutable identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

APPROVED_ORIGIN = "https://bys-user-store-578412-7a11gk0u.myshopify.com"
EXPECTED_STAGING_URL = "https://consumer-drone-agent-staging.onrender.com"
ROLLBACK_OPERATOR = "russeell"
REQUIRED_CHECKS = (
    "quality / lock",
    "quality / ruff",
    "quality / unit",
    "quality / contract",
    "quality / integration",
    "quality / build",
    "quality / config-validation",
    "quality / data-boundary",
    "quality / widget",
)
APPROVED_PRODUCTS = (
    ("Mini3", "9278439686282", "50107364802698"),
    ("Air3", "9278460821642", "50107426603146"),
    ("Mavic3", "9278439719050", "50107364901002"),
)
ALLOWED_SMOKE_METADATA = frozenset(
    {
        "status",
        "correlation_id",
        "latency_ms",
        "request_count",
        "conversation_turn_count",
        "shopify_read_count",
        "shopify_write_count",
        "checksum",
        "render_deployment_id",
        "git_sha",
    }
)
FORBIDDEN_METADATA_KEYS = (
    "authorization",
    "body",
    "cookie",
    "header",
    "password",
    "payload",
    "prompt",
    "raw",
    "request",
    "response",
    "secret",
    "text",
    "token",
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ReleaseBoundaryError(ValueError):
    """Safe release-boundary failure without credentials or raw payloads."""


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    checksum: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }


def validate_release_candidate(document: dict[str, Any]) -> ValidationResult:
    _expect(document.get("hosting_vendor") == "Render", "hosting vendor mismatch")
    _expect(document.get("service_type") == "web_service", "service type mismatch")
    _expect(document.get("runtime") == "single_container", "runtime mismatch")
    _expect(document.get("region_count") == 1, "region count mismatch")
    _expect(document.get("plan") != "free", "free Render plan is forbidden")
    _expect(document.get("kubernetes") is False, "Kubernetes is forbidden")
    _expect(document.get("multi_region") is False, "multi-region is forbidden")
    staging_url = str(document.get("staging_url", ""))
    _expect(staging_url == EXPECTED_STAGING_URL, "staging URL mismatch")
    _expect(_is_https_origin(staging_url), "staging URL must be HTTPS origin")
    _expect(
        document.get("allowed_cors_origins") == [APPROVED_ORIGIN],
        "CORS origin mismatch",
    )
    _expect(
        document.get("required_checks") == list(REQUIRED_CHECKS),
        "required check list mismatch",
    )
    _expect(
        document.get("secret_store") == "Render Environment Variables/Files",
        "hosted secret store mismatch",
    )
    _expect(
        document.get("local_credential_store") == "macOS Keychain",
        "local credential store mismatch",
    )
    git_sha = str(document.get("git_sha", ""))
    _expect(SHA40.fullmatch(git_sha) is not None, "Git SHA must be 40 lowercase hex")
    deployment_id = str(document.get("render_deployment_id", ""))
    _expect(bool(deployment_id.strip()), "Render deployment ID is required")
    image_tag = document.get("image_tag")
    if image_tag is not None:
        _expect(image_tag == f"sha-{git_sha}", "image tag must bind to full Git SHA")
    _expect(document.get("write_capable_credentials") is False, "write credential")
    _expect(document.get("external_model_calls") is False, "external model call")
    _expect(document.get("database_migration") is False, "database migration")
    _expect(document.get("force_push") is False, "force push is forbidden")
    _expect(document.get("storefront_password_protected") is True, "storefront gate")
    smoke = _validate_smoke_plan(_mapping(document.get("smoke_plan"), "smoke plan"))
    rollback = _validate_rollback_plan(
        _mapping(document.get("rollback_plan"), "rollback plan"),
        git_sha,
    )
    metadata = {
        "hosting_vendor": "Render",
        "staging_url": staging_url,
        "allowed_cors_origins": [APPROVED_ORIGIN],
        "required_checks": list(REQUIRED_CHECKS),
        "git_sha": git_sha,
        "render_deployment_id": deployment_id,
        "image_tag": image_tag,
        "smoke_plan": smoke.metadata,
        "rollback_plan": rollback.metadata,
    }
    return ValidationResult(True, _checksum(metadata), metadata)


def validate_smoke_plan(document: dict[str, Any]) -> ValidationResult:
    return _validate_smoke_plan(document)


def validate_rollback_plan(
    document: dict[str, Any],
    *,
    git_sha: str,
) -> ValidationResult:
    _expect(SHA40.fullmatch(git_sha) is not None, "Git SHA must be 40 lowercase hex")
    return _validate_rollback_plan(document, git_sha)


def redact_smoke_metadata(document: dict[str, Any]) -> ValidationResult:
    unknown = sorted(set(document) - ALLOWED_SMOKE_METADATA)
    forbidden = sorted(
        key
        for key in document
        if key not in ALLOWED_SMOKE_METADATA
        if any(fragment in key.lower() for fragment in FORBIDDEN_METADATA_KEYS)
    )
    _expect(not unknown, f"unsupported smoke metadata keys: {', '.join(unknown)}")
    _expect(not forbidden, "raw request, response, header, token, or text metadata")
    _expect(document.get("shopify_write_count", 0) == 0, "Shopify writes forbidden")
    metadata = dict(document)
    return ValidationResult(True, _checksum(metadata), metadata)


def _validate_smoke_plan(document: dict[str, Any]) -> ValidationResult:
    _expect(document.get("authority") == "single_authorized_staging_smoke", "authority")
    _expect(document.get("staging_url") == EXPECTED_STAGING_URL, "staging URL mismatch")
    _expect(document.get("allowed_origin") == APPROVED_ORIGIN, "origin mismatch")
    _expect(document.get("max_http_requests") <= 20, "HTTP request budget")
    _expect(document.get("max_conversation_turns") <= 12, "turn budget")
    _expect(document.get("max_shopify_reads_per_turn") <= 2, "read budget per turn")
    _expect(document.get("max_shopify_reads_total") <= 18, "total read budget")
    _expect(document.get("shopify_writes") == 0, "Shopify writes forbidden")
    _expect(document.get("retry_count") == 0, "retry is forbidden")
    _expect(document.get("external_model_calls") is False, "external model call")
    _expect(document.get("intent_adapter") == "deterministic_restricted", "intent")
    _expect(document.get("save_raw_payloads") is False, "raw payload storage")
    _expect(
        document.get("products") == [list(item) for item in APPROVED_PRODUCTS],
        "products",
    )
    metadata_keys = set(document.get("metadata_fields", []))
    _expect(metadata_keys <= ALLOWED_SMOKE_METADATA, "metadata field boundary")
    metadata = {
        "authority": document["authority"],
        "staging_url": document["staging_url"],
        "allowed_origin": document["allowed_origin"],
        "products": document["products"],
        "max_http_requests": document["max_http_requests"],
        "max_conversation_turns": document["max_conversation_turns"],
        "max_shopify_reads_total": document["max_shopify_reads_total"],
        "shopify_writes": 0,
        "retry_count": 0,
        "external_model_calls": False,
        "intent_adapter": "deterministic_restricted",
        "metadata_fields": sorted(metadata_keys),
    }
    return ValidationResult(True, _checksum(metadata), metadata)


def _validate_rollback_plan(document: dict[str, Any], git_sha: str) -> ValidationResult:
    _expect(document.get("operator") == ROLLBACK_OPERATOR, "rollback operator")
    _expect(document.get("window_minutes") <= 30, "rollback window")
    _expect(document.get("method") == "render_deployment_history", "rollback method")
    _expect(document.get("health_smoke_after") is True, "post-rollback health smoke")
    _expect(document.get("disable_traffic_on_failure") is True, "failure traffic stop")
    _expect(document.get("database_migration") is False, "database migration")
    _expect(document.get("destructive_data_operation") is False, "destructive data")
    previous_sha = str(document.get("previous_known_good_git_sha", ""))
    _expect(SHA40.fullmatch(previous_sha) is not None, "previous SHA identity")
    _expect(previous_sha != git_sha, "rollback target must be previous version")
    previous_deployment = str(document.get("previous_render_deployment_id", ""))
    _expect(bool(previous_deployment.strip()), "previous Render deployment required")
    metadata = {
        "operator": ROLLBACK_OPERATOR,
        "window_minutes": document["window_minutes"],
        "method": document["method"],
        "previous_known_good_git_sha": previous_sha,
        "previous_render_deployment_id": previous_deployment,
        "health_smoke_after": True,
        "disable_traffic_on_failure": True,
        "database_migration": False,
        "destructive_data_operation": False,
    }
    return ValidationResult(True, _checksum(metadata), metadata)


def _mapping(value: object, name: str) -> dict[str, Any]:
    _expect(isinstance(value, dict), f"{name} must be an object")
    return value


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseBoundaryError(message)


def _is_https_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.path.rstrip("/")
        and not parsed.query
        and not parsed.fragment
    )


def _checksum(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ReleaseBoundaryError("JSON document must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate S11 release-boundary metadata."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    candidate = subparsers.add_parser("release-candidate")
    candidate.add_argument("--config", type=Path, required=True)
    smoke = subparsers.add_parser("smoke-plan")
    smoke.add_argument("--config", type=Path, required=True)
    rollback = subparsers.add_parser("rollback-plan")
    rollback.add_argument("--config", type=Path, required=True)
    rollback.add_argument("--git-sha", required=True)
    redaction = subparsers.add_parser("redacted-smoke-metadata")
    redaction.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "release-candidate":
            result = validate_release_candidate(_read_json(args.config))
        elif args.command == "smoke-plan":
            document = _read_json(args.config)
            result = validate_smoke_plan(document.get("smoke_plan", document))
        elif args.command == "rollback-plan":
            document = _read_json(args.config)
            result = validate_rollback_plan(
                document.get("rollback_plan", document),
                git_sha=args.git_sha,
            )
        else:
            result = redact_smoke_metadata(_read_json(args.config))
    except (OSError, json.JSONDecodeError, ReleaseBoundaryError) as error:
        print(json.dumps({"accepted": False, "error": str(error)}, ensure_ascii=True))
        return 1
    print(json.dumps(result.to_dict(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
