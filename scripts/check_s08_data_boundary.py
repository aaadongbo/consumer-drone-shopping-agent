"""Check S08 no-upload and zero-write boundaries for changed repository files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.rag.data_boundary import (  # noqa: E402
    report_to_dict,
    scan_changed_data_boundary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify S08 changed files and command evidence stay metadata-only."
    )
    parser.add_argument("--base-head")
    parser.add_argument("--snapshot-head")
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help=(
            "Actual command evidence to scan for Data-Staging, Shopify, "
            "or remote Git writes."
        ),
    )
    args = parser.parse_args()

    report = scan_changed_data_boundary(
        repo_root=REPO_ROOT,
        base_head=args.base_head,
        snapshot_head=args.snapshot_head,
        commands=args.command,
    )
    print(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    return 0 if report.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
