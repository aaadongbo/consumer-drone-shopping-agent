#!/usr/bin/env python3
"""Run deterministic verification gates for one configured Slice Task."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_scope import (
    DEPENDENCY_FORBIDDEN,
    check,
    load_policy,
    resolve_task_policy,
)
from inspect_state import (
    EXPECTED_WORKFLOW_BASELINE_MARKER,
    EXPECTED_WORKFLOW_SCHEMA_VERSION,
    POLICY_RELATIVE_PATH,
    InspectionError,
    inspect,
    normalize_task_ref,
    repository_root,
)


def command_text(command: list[str]) -> str:
    return shlex.join(command)


def summarize(output: str, limit: int = 4000) -> str:
    clean = output.strip()
    if len(clean) <= limit:
        return clean
    return f"…<truncated>…\n{clean[-limit:]}"


def execute(repo: Path, command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, cwd=repo, check=False, capture_output=True, text=True
        )
        combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
        return {
            "command": command_text(command),
            "exit_code": result.returncode,
            "summary": summarize(combined),
        }
    except FileNotFoundError as exc:
        return {"command": command_text(command), "exit_code": 127, "summary": str(exc)}


def command_plan(
    task_policy: dict[str, Any],
    slice_policy: dict[str, Any],
    full: bool,
    base_head: str | None,
    snapshot_head: str | None,
    changed_paths: list[str],
) -> tuple[list[list[str]], str]:
    marker = task_policy["verification_marker"]
    rationale = task_policy["verification_rationale"]
    if full:
        marker = None
        rationale = "--full requested; running the complete pytest suite"
    pytest_command = ["uv", "run", "pytest"]
    if marker:
        pytest_command.extend(["-m", marker])
    pytest_command.append("-q")
    python_paths = sorted(path for path in changed_paths if path.endswith(".py"))
    syntax_command = [
        sys.executable,
        "-c",
        (
            "from pathlib import Path; import sys; "
            "[compile(Path(path).read_text(encoding='utf-8'), path, 'exec') "
            "for path in sys.argv[1:] if Path(path).is_file()]"
        ),
        *python_paths,
    ]
    commands = [
        syntax_command,
        ["uv", "lock", "--check"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        pytest_command,
    ]
    if base_head and snapshot_head:
        commands.extend(
            [
                ["git", "diff", "--check", base_head, snapshot_head],
                [
                    "git",
                    "diff",
                    "--quiet",
                    base_head,
                    snapshot_head,
                    "--",
                    *sorted(slice_policy["core_artifacts"]),
                ],
            ]
        )
        if task_policy["dependency_policy"] == DEPENDENCY_FORBIDDEN:
            commands.append(
                [
                    "git",
                    "diff",
                    "--quiet",
                    base_head,
                    snapshot_head,
                    "--",
                    *sorted(slice_policy["dependency_files"]),
                ]
            )
    else:
        commands.extend(
            [
                ["git", "diff", "--check"],
                ["git", "diff", "--cached", "--check"],
                [
                    "git",
                    "diff",
                    "--quiet",
                    "HEAD",
                    "--",
                    *sorted(slice_policy["core_artifacts"]),
                ],
            ]
        )
        if task_policy["dependency_policy"] == DEPENDENCY_FORBIDDEN:
            commands.append(
                [
                    "git",
                    "diff",
                    "--quiet",
                    "HEAD",
                    "--",
                    *sorted(slice_policy["dependency_files"]),
                ]
            )
    return commands, rationale


def verify(
    task_ref: str,
    repo_arg: str | Path = ".",
    *,
    full: bool = False,
    plan_only: bool = False,
    policy_path: Path | None = None,
    base_head: str | None = None,
    snapshot_head: str | None = None,
) -> dict[str, Any]:
    if bool(base_head) != bool(snapshot_head):
        raise InspectionError("base_head and snapshot_head must be supplied together")
    repo = repository_root(repo_arg)
    effective_policy_path = policy_path or repo / POLICY_RELATIVE_PATH
    state = inspect(repo, policy_path=effective_policy_path)
    task_id, canonical_task = normalize_task_ref(task_ref, state["slice_id"])
    policy = load_policy(effective_policy_path)
    slice_policy, task_policy, policy_reason = resolve_task_policy(
        state, policy, task_id
    )
    if policy_reason or slice_policy is None or task_policy is None:
        return {
            "ok": False,
            "repository_root": str(repo),
            "active_slice_tasks_file": state["tasks_file"],
            "task": canonical_task,
            "error": policy_reason or "INVALID_SCOPE_POLICY",
        }

    scope = check(
        canonical_task,
        repo,
        policy_path=effective_policy_path,
        base_head=base_head,
        snapshot_head=snapshot_head,
    )
    commands, rationale = command_plan(
        task_policy,
        slice_policy,
        full,
        base_head,
        snapshot_head,
        scope.get("changed_paths", []),
    )
    results = [] if plan_only else [execute(repo, command) for command in commands]
    commands_ok = plan_only or all(item["exit_code"] == 0 for item in results)
    return {
        "ok": bool(scope.get("ok")) and commands_ok,
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "task": canonical_task,
        "base_head": base_head,
        "snapshot_head": snapshot_head,
        "policy_identity": {
            "schema_version": policy.get("schema_version"),
            "workflow_baseline_marker": policy.get("workflow_baseline_marker"),
            "expected_schema_version": EXPECTED_WORKFLOW_SCHEMA_VERSION,
            "expected_workflow_baseline_marker": EXPECTED_WORKFLOW_BASELINE_MARKER,
        },
        "selection_rationale": rationale,
        "dependency_gate_mode": task_policy["dependency_policy"],
        "risk_policy": scope.get("risk_policy"),
        "plan_only": plan_only,
        "planned_commands": [command_text(command) for command in commands],
        "results": results,
        "scope": scope,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Task ID, for example S02-T03 or T03")
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument("--base-head", help="immutable range base commit")
    parser.add_argument("--snapshot-head", help="immutable range snapshot commit")
    parser.add_argument("--full", action="store_true", help="run full pytest suite")
    parser.add_argument("--plan-only", action="store_true", help="show gates only")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = verify(
            args.task,
            args.repo,
            full=args.full,
            plan_only=args.plan_only,
            base_head=args.base_head,
            snapshot_head=args.snapshot_head,
        )
    except (InspectionError, OSError, UnicodeError) as exc:
        payload = {"ok": False, "task": args.task.upper(), "error": str(exc)}
        print(
            json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
