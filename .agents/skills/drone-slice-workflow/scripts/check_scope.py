#!/usr/bin/env python3
"""Check a working diff or immutable commit range against Slice Task policy."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from inspect_state import (
    EXPECTED_WORKFLOW_BASELINE_MARKER,
    EXPECTED_WORKFLOW_SCHEMA_VERSION,
    POLICY_RELATIVE_PATH,
    InspectionError,
    inspect,
    normalize_task_ref,
    repository_root,
)

POLICY_PATH = (
    Path(__file__).resolve().parent.parent / "references" / "task-scope-policy.json"
)
DEPENDENCY_FORBIDDEN = "forbidden"
DEPENDENCY_PLAN_MINIMAL = "plan-authorized-minimal"
DEPENDENCY_MODES = {DEPENDENCY_FORBIDDEN, DEPENDENCY_PLAN_MINIMAL}
RISK_TIERS = {"LOW", "MEDIUM", "HIGH"}
RISK_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InspectionError(f"cannot load scope policy {path}: {exc}") from exc
    if (
        payload.get("schema_version") != EXPECTED_WORKFLOW_SCHEMA_VERSION
        or payload.get("workflow_baseline_marker") != EXPECTED_WORKFLOW_BASELINE_MARKER
        or not isinstance(payload.get("slices"), dict)
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
    if task_policy.get("dependency_policy") not in DEPENDENCY_MODES:
        return slice_policy, None, "INVALID_DEPENDENCY_POLICY"
    if task_policy.get("risk_tier") not in RISK_TIERS:
        return slice_policy, None, "INVALID_RISK_TIER"
    if task_policy.get("checkpoint_policy") != "human-decision":
        return slice_policy, None, "INVALID_CHECKPOINT_POLICY"
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
    return {
        "all": sorted(set(staged + unstaged + untracked)),
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }


def range_paths(repo: Path, base_head: str, snapshot_head: str) -> list[str]:
    return git_paths(
        repo,
        "diff",
        "--name-only",
        "--no-renames",
        base_head,
        snapshot_head,
    )


def path_allowed(path: str, patterns: list[str]) -> bool:
    return any(
        path.startswith(pattern) if pattern.endswith("/") else path == pattern
        for pattern in patterns
    )


def policy_error(
    repo: Path, state: dict[str, Any], task_ref: str, reason: str
) -> dict[str, Any]:
    return {
        "ok": False,
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "task": task_ref,
        "error": reason,
        "blocking_reasons": [reason],
    }


def check(
    task_ref: str,
    repo_arg: str | Path = ".",
    *,
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
    task = next((item for item in state["tasks"] if item["id"] == task_id), None)
    if task is None:
        return policy_error(repo, state, canonical_task, "ILLEGAL_OR_UNKNOWN_TASK_ID")

    policy = load_policy(effective_policy_path)
    slice_policy, task_policy, policy_reason = resolve_task_policy(
        state, policy, task_id
    )
    if policy_reason or slice_policy is None or task_policy is None:
        return policy_error(
            repo, state, canonical_task, policy_reason or "INVALID_SCOPE_POLICY"
        )

    immutable_range = base_head is not None and snapshot_head is not None
    if immutable_range:
        paths = {
            "all": range_paths(repo, base_head, snapshot_head),
            "staged": [],
            "unstaged": [],
            "untracked": [],
        }
    else:
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
    risk_escalation_paths = sorted(
        path
        for path in paths["all"]
        if path_allowed(path, list(slice_policy.get("risk_escalation_paths", [])))
    )
    effective_tier = "HIGH" if risk_escalation_paths else task_policy["risk_tier"]
    other_dirty = [
        {"path": item["path"], "dirty_paths": item["dirty_paths"]}
        for item in state["worktrees"]
        if not item["current"] and item["dirty_paths"]
    ]

    reasons: list[str] = []
    if task["status"] not in {"IN_PROGRESS", "DONE"}:
        reasons.append("TASK_NOT_ACTIVE_OR_DONE")
    if not task["ordered_dependency_satisfied"]:
        reasons.append("DEPENDENCY_NOT_SATISFIED")
    if not task["implementation_gate"]["satisfied"]:
        reasons.extend(task["implementation_gate"]["blocking_reasons"])
    if not paths["all"]:
        reasons.append("NO_TASK_CHANGES")
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
            "Only minimal dependencies directly required by the approved Task/plan "
            "are allowed; major or cross-Slice dependencies require Human escalation."
            if dependency_allowed
            else "Dependency changes are not authorized for this Task."
        ),
    }
    return {
        "ok": not reasons,
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "slice": state["slice_id"],
        "task": canonical_task,
        "local_task": task_id,
        "task_status": task["status"],
        "ordered_dependency_satisfied": bool(task["ordered_dependency_satisfied"]),
        "implementation_gate": task["implementation_gate"],
        "scope_policy_file": str(effective_policy_path),
        "immutable_range": immutable_range,
        "base_head": base_head,
        "snapshot_head": snapshot_head,
        "allowed_patterns": allowed_patterns,
        "changed_paths": paths["all"],
        "staged_paths": paths["staged"],
        "unstaged_paths": paths["unstaged"],
        "untracked_paths": paths["untracked"],
        "disallowed_paths": disallowed,
        "core_artifact_changes": core_changes,
        "dependency_review": dependency_review,
        "forbidden_slice_path_changes": forbidden_prefix_changes,
        "risk_policy": {
            "minimum_tier": task_policy["risk_tier"],
            "effective_tier": effective_tier,
            "checkpoint_policy": task_policy["checkpoint_policy"],
            "deterministic_escalation_paths": risk_escalation_paths,
            "semantic_review_required": True,
        },
        "other_dirty_worktrees": other_dirty,
        "blocking_reasons": list(dict.fromkeys(reasons)),
    }


def check_slice_range(
    task_ref: str,
    repo_arg: str | Path = ".",
    *,
    policy_path: Path | None = None,
    base_head: str,
    snapshot_head: str,
) -> dict[str, Any]:
    """Validate a complete Slice range against the union of configured Task scopes."""
    repo = repository_root(repo_arg)
    effective_policy_path = policy_path or repo / POLICY_RELATIVE_PATH
    state = inspect(repo, policy_path=effective_policy_path)
    task_id, canonical_task = normalize_task_ref(task_ref, state["slice_id"])
    task = next((item for item in state["tasks"] if item["id"] == task_id), None)
    if task is None:
        return policy_error(repo, state, canonical_task, "ILLEGAL_OR_UNKNOWN_TASK_ID")

    policy = load_policy(effective_policy_path)
    slice_policy = policy["slices"].get(state["tasks_file"])
    if not isinstance(slice_policy, dict):
        return policy_error(repo, state, canonical_task, "UNCONFIGURED_SLICE_POLICY")
    configured_tasks = slice_policy.get("tasks")
    if not isinstance(configured_tasks, dict):
        return policy_error(repo, state, canonical_task, "INVALID_SLICE_TASK_POLICY")
    completion_task = slice_policy.get("completion_task")
    if completion_task not in configured_tasks:
        return policy_error(
            repo, state, canonical_task, "INVALID_COMPLETION_TASK_POLICY"
        )
    if task_id != completion_task:
        return policy_error(
            repo, state, canonical_task, "SLICE_REVIEW_TASK_IDENTITY_MISMATCH"
        )
    state_task_ids = {item["id"] for item in state["tasks"]}
    if set(configured_tasks) != state_task_ids:
        return policy_error(
            repo, state, canonical_task, "SLICE_TASK_POLICY_IDENTITY_MISMATCH"
        )

    task_policies: list[dict[str, Any]] = []
    for configured_task_id in sorted(configured_tasks):
        _, task_policy, reason = resolve_task_policy(state, policy, configured_task_id)
        if reason or task_policy is None:
            return policy_error(
                repo,
                state,
                canonical_task,
                reason or "INVALID_SLICE_TASK_POLICY",
            )
        task_policies.append(task_policy)

    paths = range_paths(repo, base_head, snapshot_head)
    allowed_patterns = sorted(
        {
            pattern
            for task_policy in task_policies
            for pattern in task_policy["allowed_paths"]
        }
    )
    dependency_files = set(slice_policy["dependency_files"])
    dependency_changes = sorted(dependency_files.intersection(paths))
    dependency_allowed = any(
        task_policy["dependency_policy"] == DEPENDENCY_PLAN_MINIMAL
        for task_policy in task_policies
    )
    disallowed = [
        path
        for path in paths
        if not path_allowed(path, allowed_patterns)
        and not (dependency_allowed and path in dependency_files)
    ]
    core_changes = sorted(set(slice_policy["core_artifacts"]).intersection(paths))
    forbidden_prefix_changes = sorted(
        path
        for path in paths
        if any(
            path.startswith(prefix)
            for prefix in slice_policy["forbidden_path_prefixes"]
        )
        and not path_allowed(path, allowed_patterns)
    )
    risk_escalation_paths = sorted(
        path
        for path in paths
        if path_allowed(path, list(slice_policy.get("risk_escalation_paths", [])))
    )
    aggregate_tier = max(
        (task_policy["risk_tier"] for task_policy in task_policies),
        key=RISK_RANK.__getitem__,
    )
    effective_tier = "HIGH" if risk_escalation_paths else aggregate_tier

    reasons: list[str] = []
    if any(item["status"] != "DONE" for item in state["tasks"]):
        reasons.append("SLICE_NOT_COMPLETE")
    if not task["implementation_gate"]["satisfied"]:
        reasons.extend(task["implementation_gate"]["blocking_reasons"])
    if not paths:
        reasons.append("NO_SLICE_CHANGES")
    if disallowed:
        reasons.append("PATH_OUTSIDE_SLICE_SCOPE")
    if core_changes:
        reasons.append("CORE_ARTIFACT_CHANGED")
    if dependency_changes and not dependency_allowed:
        reasons.append("DEPENDENCY_FILE_CHANGED_WITHOUT_SLICE_POLICY")
    if forbidden_prefix_changes:
        reasons.append("FORBIDDEN_SLICE_PATH_CHANGED")

    other_dirty = [
        {"path": item["path"], "dirty_paths": item["dirty_paths"]}
        for item in state["worktrees"]
        if not item["current"] and item["dirty_paths"]
    ]
    return {
        "ok": not reasons,
        "scope_kind": "slice-range",
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "slice": state["slice_id"],
        "task": canonical_task,
        "local_task": task_id,
        "task_status": task["status"],
        "all_tasks_done": all(item["status"] == "DONE" for item in state["tasks"]),
        "implementation_gate": task["implementation_gate"],
        "scope_policy_file": str(effective_policy_path),
        "immutable_range": True,
        "base_head": base_head,
        "snapshot_head": snapshot_head,
        "configured_tasks": sorted(configured_tasks),
        "completion_task": completion_task,
        "allowed_patterns": allowed_patterns,
        "changed_paths": paths,
        "staged_paths": [],
        "unstaged_paths": [],
        "untracked_paths": [],
        "disallowed_paths": disallowed,
        "core_artifact_changes": core_changes,
        "dependency_review": {
            "mode": "slice-task-scope-union",
            "changed_paths": dependency_changes,
            "allowed_by_task_policy": dependency_allowed,
            "manual_confirmation_required": bool(dependency_changes),
            "condition": (
                "Only dependencies authorized by at least one configured Slice Task "
                "are in scope; major or cross-Slice changes require Human escalation."
                if dependency_allowed
                else "Dependency changes are not authorized by this Slice."
            ),
        },
        "forbidden_slice_path_changes": forbidden_prefix_changes,
        "risk_policy": {
            "minimum_tier": aggregate_tier,
            "effective_tier": effective_tier,
            "checkpoint_policy": "human-decision",
            "deterministic_escalation_paths": risk_escalation_paths,
            "semantic_review_required": True,
            "human_decision_required": effective_tier == "HIGH",
        },
        "other_dirty_worktrees": other_dirty,
        "blocking_reasons": list(dict.fromkeys(reasons)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Task ID, for example S02-T03 or T03")
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument("--base-head", help="immutable range base commit")
    parser.add_argument("--snapshot-head", help="immutable range snapshot commit")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = check(
            args.task,
            args.repo,
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
