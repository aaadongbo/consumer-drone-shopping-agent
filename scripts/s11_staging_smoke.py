"""Restricted S11 staging smoke runner.

The live mode makes only health/readiness HTTP requests to the approved staging
URL with the approved storefront Origin. It records metadata only and never
stores request/response bodies, headers, credentials, or user text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from s11_release_boundary import (
    APPROVED_ORIGIN,
    EXPECTED_STAGING_URL,
    redact_smoke_metadata,
    validate_release_candidate,
)

SMOKE_PATHS = ("/healthz", "/readyz")


@dataclass(frozen=True, slots=True)
class SmokeResult:
    status: str
    request_count: int
    conversation_turn_count: int
    shopify_read_count: int
    shopify_write_count: int
    latency_ms: int
    checksum: str
    correlation_id: str

    def to_metadata(self) -> dict[str, object]:
        return {
            "status": self.status,
            "request_count": self.request_count,
            "conversation_turn_count": self.conversation_turn_count,
            "shopify_read_count": self.shopify_read_count,
            "shopify_write_count": self.shopify_write_count,
            "latency_ms": self.latency_ms,
            "checksum": self.checksum,
            "correlation_id": self.correlation_id,
        }


def run_metadata_smoke(config: dict[str, Any]) -> SmokeResult:
    candidate = validate_release_candidate(config)
    metadata = candidate.metadata["smoke_plan"]
    payload = {
        "status": "metadata_ready",
        "staging_url": EXPECTED_STAGING_URL,
        "allowed_origin": APPROVED_ORIGIN,
        "products": metadata["products"],
        "request_count": 0,
        "conversation_turn_count": 0,
        "shopify_read_count": 0,
        "shopify_write_count": 0,
    }
    checksum = _checksum(payload)
    return SmokeResult(
        status="metadata_ready",
        request_count=0,
        conversation_turn_count=0,
        shopify_read_count=0,
        shopify_write_count=0,
        latency_ms=0,
        checksum=checksum,
        correlation_id=f"s11-smoke-{checksum[:12]}",
    )


def run_live_health_smoke(config: dict[str, Any]) -> SmokeResult:
    validate_release_candidate(config)
    started = time.monotonic()
    statuses: list[int] = []
    for path in SMOKE_PATHS:
        request = Request(
            f"{EXPECTED_STAGING_URL}{path}",
            headers={"Origin": APPROVED_ORIGIN},
            method="GET",
        )
        try:
            with urlopen(request, timeout=5) as response:
                statuses.append(response.status)
        except URLError as error:
            reason = type(error.reason).__name__
            raise RuntimeError(f"staging smoke failed: {reason}") from error
    elapsed = int((time.monotonic() - started) * 1000)
    status = "pass" if statuses == [200, 200] else "failed"
    return _result(status=status, request_count=len(statuses), latency_ms=elapsed)


def _result(*, status: str, request_count: int, latency_ms: int) -> SmokeResult:
    payload = _metadata(status, request_count, latency_ms)
    checksum = _checksum(payload)
    return SmokeResult(
        status=status,
        request_count=request_count,
        conversation_turn_count=0,
        shopify_read_count=0,
        shopify_write_count=0,
        latency_ms=latency_ms,
        checksum=checksum,
        correlation_id=f"s11-smoke-{checksum[:12]}",
    )


def _metadata(status: str, request_count: int, latency_ms: int) -> dict[str, object]:
    return {
        "status": status,
        "request_count": request_count,
        "conversation_turn_count": 0,
        "shopify_read_count": 0,
        "shopify_write_count": 0,
        "latency_ms": latency_ms,
    }


def _checksum(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("JSON document must be an object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Run S11 restricted staging smoke.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            run_live_health_smoke(_read_json(args.config))
            if args.live
            else run_metadata_smoke(_read_json(args.config))
        )
        metadata = result.to_metadata()
        redact_smoke_metadata(metadata)
    except Exception as error:
        print(json.dumps({"accepted": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"accepted": True, "metadata": metadata}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
