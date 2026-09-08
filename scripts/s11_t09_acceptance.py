"""Local, credential-free T09 acceptance guard.

This command intentionally validates only the local application/widget boundary.
Live Shopify/browser acceptance requires a separately authorized budget and is
never implied by this script.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def inspect_assets(root: Path) -> dict[str, object]:
    javascript = (root / "storefront" / "assets" / "presales-widget.js").read_text()
    stylesheet = (root / "storefront" / "assets" / "presales-widget.css").read_text()
    return {
        "conversation_api_only": "/v1/conversation/turn" in javascript,
        "credential_free": "Authorization" not in javascript,
        "wildcard_cors_absent": '"*"' not in javascript,
        "navigation_reset": "presales:navigate" in javascript,
        "support_destination_is_host_supplied": "data-support-url" in javascript,
        "admin_support_destination_absent": "admin.shopify.com" not in javascript,
        "responsive_css": "max-width: 480px" in stylesheet,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    checks = inspect_assets(args.root)
    print({"mode": "local-only", "checks": checks, "live_smoke": "NOT_RUN"})
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
