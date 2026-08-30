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
    POLICY_PATH,
    check,
    load_policy,
    resolve_task_policy,
)
from inspect_state import InspectionError, inspect, repository_root


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
            command,
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
        return {
            "command": command_text(command),
            "exit_code": result.returncode,
            "summary": summarize(combined),
        }
    except FileNotFoundError as exc:
        return {
            "command": command_text(command),
            "exit_code": 127,
            "summary": str(exc),
        }


def command_plan(
    task_policy: dict[str, Any],
    slice_policy: dict[str, Any],
    full: bool,
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
    commands = [
        ["uv", "lock", "--check"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        pytest_command,
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
    task_id: str,
    repo_arg: str | Path = ".",
    *,
    full: bool = False,
    plan_only: bool = False,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    task_id = task_id.upper()
    repo = repository_root(repo_arg)
    state = inspect(repo)
    policy = load_policy(policy_path)
    slice_policy, task_policy, policy_reason = resolve_task_policy(
        state, policy, task_id
    )
    if policy_reason or slice_policy is None or task_policy is None:
        return {
            "ok": False,
            "repository_root": str(repo),
            "active_slice_tasks_file": state["tasks_file"],
            "task": task_id,
            "error": policy_reason or "INVALID_SCOPE_POLICY",
        }

    scope = check(task_id, repo, policy_path=policy_path)
    commands, rationale = command_plan(task_policy, slice_policy, full)
    results = [] if plan_only else [execute(repo, command) for command in commands]
    commands_ok = plan_only or all(item["exit_code"] == 0 for item in results)
    return {
        "ok": bool(scope.get("ok")) and commands_ok,
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "task": task_id,
        "selection_rationale": rationale,
        "dependency_gate_mode": task_policy["dependency_policy"],
        "plan_only": plan_only,
        "planned_commands": [command_text(command) for command in commands],
        "results": results,
        "scope": scope,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Task ID, for example T06")
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument("--full", action="store_true", help="run full pytest suite")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="show selected gates without running them",
    )
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
