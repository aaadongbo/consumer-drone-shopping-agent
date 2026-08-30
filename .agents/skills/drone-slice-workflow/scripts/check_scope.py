#!/usr/bin/env python3
"""Check the current diff against the active Slice and Task policy."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from inspect_state import InspectionError, inspect, repository_root

POLICY_PATH = (
    Path(__file__).resolve().parent.parent / "references" / "task-scope-policy.json"
)
DEPENDENCY_FORBIDDEN = "forbidden"
DEPENDENCY_PLAN_MINIMAL = "plan-authorized-minimal"
DEPENDENCY_MODES = {DEPENDENCY_FORBIDDEN, DEPENDENCY_PLAN_MINIMAL}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InspectionError(f"cannot load scope policy {path}: {exc}") from exc
    if payload.get("schema_version") != 1 or not isinstance(
        payload.get("slices"), dict
    ):
        raise InspectionError(f"unsupported scope policy schema in {path}")
    return payload


def resolve_task_policy(
    state: dict[str, Any], policy: dict[str, Any], task_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    slice_policy = policy["slices"].get(state["tasks_file"])
    if not isinstance(slice_policy, dict):
        return None, None, "UNCONFIGURED_SLICE_POLICY"
    task_policy = slice_policy.get("tasks", {}).get(task_id)
    if not isinstance(task_policy, dict):
        return slice_policy, None, "UNCONFIGURED_TASK_POLICY"
    dependency_mode = task_policy.get("dependency_policy")
    if dependency_mode not in DEPENDENCY_MODES:
        return slice_policy, None, "INVALID_DEPENDENCY_POLICY"
    return slice_policy, task_policy, None


def git_paths(repo: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args, "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise InspectionError(result.stderr.decode(errors="replace").strip())
    return sorted(
        {
            value.decode(errors="surrogateescape")
            for value in result.stdout.split(b"\0")
            if value
        }
    )


def changed_paths(repo: Path) -> dict[str, list[str]]:
    staged = git_paths(repo, "diff", "--cached", "--name-only")
    unstaged = git_paths(repo, "diff", "--name-only")
    untracked = git_paths(repo, "ls-files", "--others", "--exclude-standard")
    all_paths = sorted(set(staged + unstaged + untracked))
    return {
        "all": all_paths,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }


def path_allowed(path: str, patterns: list[str]) -> bool:
    return any(
        path.startswith(pattern) if pattern.endswith("/") else path == pattern
        for pattern in patterns
    )


def policy_error(
    repo: Path,
    state: dict[str, Any],
    task_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "task": task_id,
        "error": reason,
        "blocking_reasons": [reason],
    }


def check(
    task_id: str,
    repo_arg: str | Path = ".",
    *,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    task_id = task_id.upper()
    repo = repository_root(repo_arg)
    state = inspect(repo)
    task = next((item for item in state["tasks"] if item["id"] == task_id), None)
    if task is None:
        return policy_error(repo, state, task_id, "ILLEGAL_OR_UNKNOWN_TASK_ID")

    policy = load_policy(policy_path)
    slice_policy, task_policy, policy_reason = resolve_task_policy(
        state, policy, task_id
    )
    if policy_reason or slice_policy is None or task_policy is None:
        return policy_error(
            repo,
            state,
            task_id,
            policy_reason or "INVALID_SCOPE_POLICY",
        )

    paths = changed_paths(repo)
    allowed_patterns = list(task_policy["allowed_paths"])
    dependency_files = set(slice_policy["dependency_files"])
    dependency_mode = task_policy["dependency_policy"]
    dependency_changes = sorted(dependency_files.intersection(paths["all"]))
    dependency_allowed = dependency_mode == DEPENDENCY_PLAN_MINIMAL
    disallowed = [
        path
        for path in paths["all"]
        if not path_allowed(path, allowed_patterns)
        and not (dependency_allowed and path in dependency_files)
    ]
    core_changes = sorted(
        set(slice_policy["core_artifacts"]).intersection(paths["all"])
    )
    forbidden_prefix_changes = sorted(
        path
        for path in paths["all"]
        if any(
            path.startswith(prefix)
            for prefix in slice_policy["forbidden_path_prefixes"]
        )
        and not path_allowed(path, allowed_patterns)
    )
    other_dirty = [
        {"path": worktree["path"], "dirty_paths": worktree["dirty_paths"]}
        for worktree in state["worktrees"]
        if not worktree["current"] and worktree["dirty_paths"]
    ]
    reasons: list[str] = []
    if task["status"] not in {"IN_PROGRESS", "DONE"}:
        reasons.append("TASK_NOT_ACTIVE_OR_DONE")
    if not task["dependency_satisfied"]:
        reasons.append("DEPENDENCY_NOT_SATISFIED")
    if disallowed:
        reasons.append("PATH_OUTSIDE_TASK_SCOPE")
    if core_changes:
        reasons.append("CORE_ARTIFACT_CHANGED")
    if dependency_changes and not dependency_allowed:
        reasons.append("DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY")
    if forbidden_prefix_changes:
        reasons.append("FORBIDDEN_SLICE_PATH_CHANGED")

    dependency_review = {
        "mode": dependency_mode,
        "changed_paths": dependency_changes,
        "allowed_by_task_policy": dependency_allowed,
        "manual_confirmation_required": bool(dependency_changes),
        "condition": (
            "Only minimal dependencies directly required by the approved Task/plan are "
            "allowed; major or cross-Slice dependencies require Human escalation."
            if dependency_allowed
            else "Dependency changes are not authorized for this Task."
        ),
    }
    return {
        "ok": not reasons,
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "scope_policy_file": str(policy_path),
        "task": task_id,
        "task_status": task["status"],
        "dependency_satisfied": bool(task["dependency_satisfied"]),
        "allowed_patterns": allowed_patterns,
        "changed_paths": paths["all"],
        "staged_paths": paths["staged"],
        "unstaged_paths": paths["unstaged"],
        "untracked_paths": paths["untracked"],
        "disallowed_paths": disallowed,
        "core_artifact_changes": core_changes,
        "dependency_review": dependency_review,
        "forbidden_slice_path_changes": forbidden_prefix_changes,
        "other_dirty_worktrees": other_dirty,
        "blocking_reasons": reasons,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Task ID, for example T06")
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = check(args.task, args.repo)
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
