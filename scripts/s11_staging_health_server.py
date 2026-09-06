"""Tiny stdlib health wrapper for the S11 Render staging container.

The repository does not add an ASGI server dependency in T06. This wrapper
keeps deployment health/readiness checks metadata-only until a separately
approved runtime server dependency or host-provided command exists.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from s11_release_boundary import APPROVED_ORIGIN, EXPECTED_STAGING_URL


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "consumer-drone-agent-s11"

    def do_GET(self) -> None:
        if self.path not in {"/healthz", "/readyz"}:
            self.send_error(404)
            return
        configured_origin = os.environ.get("DRONE_WIDGET_ORIGINS", "")
        status = 200 if configured_origin == APPROVED_ORIGIN else 503
        body = {
            "status": "ok" if status == 200 else "not_ready",
            "staging_url": EXPECTED_STAGING_URL,
            "allowed_origin_configured": configured_origin == APPROVED_ORIGIN,
            "credential_values_exposed": False,
            "shopify_write_count": 0,
        }
        payload = json.dumps(body, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> int:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
