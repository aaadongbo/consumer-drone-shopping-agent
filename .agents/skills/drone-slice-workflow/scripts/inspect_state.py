#!/usr/bin/env python3
"""Inspect Git/worktree and ordered Slice Task state without modifying files."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TASK_ROW = re.compile(
    r"^\|\s*(T\d{2})\s*\|\s*(.*?)\s*\|\s*"
    r"(NOT_STARTED|IN_PROGRESS|BLOCKED|DONE)\s*\|\s*(.*?)\s*\|$"
)
TASK_ID = re.compile(r"T\d{2}")
SLICE_DIR = re.compile(r"^slice-(\d{2})-")
CANONICAL_TASK = re.compile(r"^(S\d{2})-(T\d{2})$")
POLICY_RELATIVE_PATH = Path(
    ".agents/skills/drone-slice-workflow/references/task-scope-policy.json"
)
EXPECTED_WORKFLOW_SCHEMA_VERSION = 3
EXPECTED_WORKFLOW_BASELINE_MARKER = "workflow-simplification-v2"
DEFAULT_PROTECTED_REFS = {
    "refs/heads/main",
    "refs/heads/master",
    "refs/remotes/*/main",
    "refs/remotes/*/master",
}
WORKFLOW_GATED_TASK_FILES = {
    "changes/slice-02-single-turn-recommendation/tasks.md",
}


class InspectionError(RuntimeError):
    """Raised when repository state cannot be inspected reliably."""


def run_git(
    repo: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise InspectionError(f"git {' '.join(args)}: {message}")
    return result


def repository_root(candidate: str | Path = ".") -> Path:
    path = Path(candidate).resolve()
    result = run_git(path, "rev-parse", "--show-toplevel")
    return Path(result.stdout.strip()).resolve()


def porcelain_paths(repo: Path, *extra: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "-z", *extra],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise InspectionError(result.stderr.decode(errors="replace").strip())
    entries = result.stdout.split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        decoded = entry.decode(errors="surrogateescape")
        status = decoded[:2]
        path = decoded[3:]
        if status[0] in {"R", "C"} and index < len(entries):
            renamed_to = entries[index].decode(errors="surrogateescape")
            index += 1
            paths.extend([path, renamed_to])
        else:
            paths.append(path)
    return sorted(set(paths))


def find_tasks_file(repo: Path) -> Path:
    candidates = sorted((repo / "changes").glob("*/tasks.md"))
    if not candidates:
        raise InspectionError("no changes/*/tasks.md found")
    parsed = [(path, parse_tasks(path)) for path in candidates]
    active = [
        path
        for path, tasks in parsed
        if any(task["status"] == "IN_PROGRESS" for task in tasks)
    ]
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        relative = [str(path.relative_to(repo)) for path in active]
        raise InspectionError(f"multiple Slices contain active Tasks: {relative}")
    incomplete = [
        path
        for path, tasks in parsed
        if any(task["status"] != "DONE" for task in tasks)
    ]
    if len(incomplete) == 1:
        return incomplete[0]
    if len(incomplete) > 1:
        relative = [str(path.relative_to(repo)) for path in incomplete]
        raise InspectionError(f"multiple incomplete Slice task files: {relative}")
    return parsed[-1][0]


def parse_tasks(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TASK_ROW.match(line)
        if not match:
            continue
        task_id, title, status, dependency_cell = match.groups()
        tasks.append(
            {
                "id": task_id,
                "title": title,
                "status": status,
                "dependencies": TASK_ID.findall(dependency_cell),
                "dependency_text": dependency_cell,
            }
        )
    if not tasks:
        raise InspectionError(f"no Task status rows found in {path}")
    if len({task["id"] for task in tasks}) != len(tasks):
        raise InspectionError(f"duplicate Task IDs in {path}")
    return tasks


def slice_id_from_tasks_file(tasks_file: str | Path) -> str:
    directory = Path(tasks_file).parent.name
    match = SLICE_DIR.match(directory)
    if not match:
        raise InspectionError(f"cannot derive Slice ID from {tasks_file}")
    return f"S{match.group(1)}"


def normalize_task_ref(task_ref: str, slice_id: str) -> tuple[str, str]:
    normalized = task_ref.strip().upper()
    if TASK_ID.fullmatch(normalized):
        return normalized, f"{slice_id}-{normalized}"
    match = CANONICAL_TASK.fullmatch(normalized)
    if not match:
        raise InspectionError(f"invalid Task reference: {task_ref}")
    requested_slice, local_task = match.groups()
    if requested_slice != slice_id:
        raise InspectionError(
            f"Task Slice mismatch: active {slice_id}, requested {requested_slice}"
        )
    return local_task, normalized


def load_policy_document(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InspectionError(f"cannot load scope policy {path}: {exc}") from exc
    if not isinstance(payload.get("slices"), dict):
        raise InspectionError(f"invalid scope policy in {path}")
    return payload


def load_revision_policy(
    repo: Path, revision: str
) -> tuple[dict[str, Any] | None, str | None]:
    result = run_git(
        repo,
        "show",
        f"{revision}:{POLICY_RELATIVE_PATH.as_posix()}",
        check=False,
    )
    if result.returncode != 0:
        return None, "WORKFLOW_POLICY_NOT_PRESENT_AT_REVISION"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "WORKFLOW_POLICY_INVALID_AT_REVISION"
    return payload, None


def revision_policy_blob(repo: Path, revision: str) -> str | None:
    result = run_git(
        repo,
        "rev-parse",
        "--verify",
        f"{revision}:{POLICY_RELATIVE_PATH.as_posix()}",
        check=False,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def protected_ref_patterns(policy: dict[str, Any]) -> list[str]:
    configured = policy.get("protected_refs", [])
    if not isinstance(configured, list) or not all(
        isinstance(item, str) and item.startswith("refs/") for item in configured
    ):
        raise InspectionError("protected_refs must be a list of refs/* patterns")
    return sorted(DEFAULT_PROTECTED_REFS.union(configured))


def protected_refs(repo: Path, policy: dict[str, Any]) -> list[str]:
    patterns = protected_ref_patterns(policy)
    refs = run_git(repo, "for-each-ref", "--format=%(refname)").stdout.splitlines()
    return sorted(
        ref
        for ref in refs
        if any(fnmatch.fnmatchcase(ref, pattern) for pattern in patterns)
    )


def fixed_policy_valid(policy: dict[str, Any] | None, tasks_file: str) -> bool:
    return bool(
        policy
        and policy.get("schema_version") == EXPECTED_WORKFLOW_SCHEMA_VERSION
        and policy.get("workflow_baseline_marker") == EXPECTED_WORKFLOW_BASELINE_MARKER
        and tasks_file in policy.get("slices", {})
    )


def implementation_gate(
    repo: Path,
    tasks_file: str,
    slice_policy: dict[str, Any] | None,
    policy: dict[str, Any],
    approved_workflow_oid: str | None,
) -> dict[str, Any]:
    if slice_policy is None:
        return {
            "satisfied": False,
            "type": None,
            "blocking_reasons": ["UNCONFIGURED_SLICE_POLICY"],
        }
    gate = slice_policy.get("implementation_gate")
    if gate is None:
        if tasks_file in WORKFLOW_GATED_TASK_FILES:
            return {
                "satisfied": False,
                "type": None,
                "blocking_reasons": ["REQUIRED_IMPLEMENTATION_GATE_MISSING"],
            }
        return {"satisfied": True, "type": None, "blocking_reasons": []}
    if gate.get("type") != "protected-workflow-baseline":
        return {
            "satisfied": False,
            "type": gate.get("type"),
            "blocking_reasons": ["INVALID_IMPLEMENTATION_GATE"],
        }
    reasons: list[str] = []
    if policy.get("schema_version") != EXPECTED_WORKFLOW_SCHEMA_VERSION:
        reasons.append("WORKFLOW_POLICY_SCHEMA_MISMATCH")
    if policy.get("workflow_baseline_marker") != EXPECTED_WORKFLOW_BASELINE_MARKER:
        reasons.append("WORKFLOW_BASELINE_MARKER_MISMATCH")

    head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    head_policy_blob = revision_policy_blob(repo, head)
    integrated: list[dict[str, str]] = []
    for ref in protected_refs(repo, policy):
        ref_oid = run_git(repo, "rev-parse", ref).stdout.strip()
        is_ancestor = (
            run_git(
                repo, "merge-base", "--is-ancestor", ref_oid, head, check=False
            ).returncode
            == 0
        )
        ref_policy, _ = load_revision_policy(repo, ref)
        ref_policy_blob = revision_policy_blob(repo, ref)
        if (
            is_ancestor
            and fixed_policy_valid(ref_policy, tasks_file)
            and head_policy_blob
            and head_policy_blob == ref_policy_blob
        ):
            integrated.append({"ref": ref, "oid": ref_oid})

    approved: dict[str, str] | None = None
    if approved_workflow_oid:
        resolved = run_git(
            repo,
            "rev-parse",
            "--verify",
            f"{approved_workflow_oid}^{{commit}}",
            check=False,
        )
        if resolved.returncode != 0:
            reasons.append("HUMAN_APPROVED_WORKFLOW_OID_INVALID")
        else:
            approved_oid = resolved.stdout.strip()
            approved_policy, _ = load_revision_policy(repo, approved_oid)
            approved_is_ancestor = (
                run_git(
                    repo,
                    "merge-base",
                    "--is-ancestor",
                    approved_oid,
                    head,
                    check=False,
                ).returncode
                == 0
            )
            approved_blob = revision_policy_blob(repo, approved_oid)
            if (
                not approved_is_ancestor
                or not fixed_policy_valid(approved_policy, tasks_file)
                or not head_policy_blob
                or head_policy_blob != approved_blob
            ):
                reasons.append("HUMAN_APPROVED_WORKFLOW_OID_MISMATCH")
            else:
                approved = {"oid": approved_oid, "source": "current-context"}

    if not (integrated or approved):
        reasons.append("WORKFLOW_BASELINE_NOT_PROTECTED_OR_HUMAN_APPROVED")
    return {
        "satisfied": not reasons,
        "type": gate["type"],
        "required_schema_version": EXPECTED_WORKFLOW_SCHEMA_VERSION,
        "required_marker": EXPECTED_WORKFLOW_BASELINE_MARKER,
        "protected_patterns": protected_ref_patterns(policy),
        "integrated_baselines": integrated,
        "human_approved_baseline": approved,
        "blocking_reasons": list(dict.fromkeys(reasons)),
    }


def parse_worktrees(repo: Path) -> list[dict[str, Any]]:
    result = run_git(repo, "worktree", "list", "--porcelain")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines() + [""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value

    current_root = repo.resolve()
    worktrees: list[dict[str, Any]] = []
    for record in records:
        path = Path(record["worktree"]).resolve()
        try:
            dirty_paths = porcelain_paths(path)
        except InspectionError as exc:
            dirty_paths = [f"<inspection-error: {exc}>"]
        active_refs: list[str] = []
        tasks_file: str | None = None
        try:
            located = find_tasks_file(path)
            tasks_file = str(located.relative_to(path))
            slice_id = slice_id_from_tasks_file(tasks_file)
            active_refs = [
                f"{slice_id}-{task['id']}"
                for task in parse_tasks(located)
                if task["status"] == "IN_PROGRESS"
            ]
        except (InspectionError, OSError, UnicodeError):
            pass
        worktrees.append(
            {
                "path": str(path),
                "head": record.get("HEAD"),
                "branch": record.get("branch"),
                "detached": "detached" in record,
                "current": path == current_root,
                "dirty_paths": dirty_paths,
                "tasks_file": tasks_file,
                "active_task_refs": active_refs,
                "active_tasks": [ref.split("-", 1)[1] for ref in active_refs],
            }
        )
    return worktrees


def inspect(
    repo_arg: str | Path = ".",
    *,
    implementation_authorized_task: str | None = None,
    approved_workflow_oid: str | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    repo = repository_root(repo_arg)
    tasks_path = find_tasks_file(repo)
    tasks_file = str(tasks_path.relative_to(repo))
    slice_id = slice_id_from_tasks_file(tasks_file)
    tasks = parse_tasks(tasks_path)
    status_by_id = {task["id"]: task["status"] for task in tasks}
    effective_policy_path = policy_path or repo / POLICY_RELATIVE_PATH
    policy = load_policy_document(effective_policy_path)
    slice_policy = policy["slices"].get(tasks_file)
    gate = implementation_gate(
        repo, tasks_file, slice_policy, policy, approved_workflow_oid
    )

    authorized_canonical: str | None = None
    if implementation_authorized_task:
        _, authorized_canonical = normalize_task_ref(
            implementation_authorized_task, slice_id
        )

    for task in tasks:
        missing = [dep for dep in task["dependencies"] if dep not in status_by_id]
        unsatisfied = [
            dep for dep in task["dependencies"] if status_by_id.get(dep) != "DONE"
        ]
        canonical = f"{slice_id}-{task['id']}"
        task.update(
            {
                "canonical_id": canonical,
                "ordered_dependency_satisfied": not missing and not unsatisfied,
                "dependency_satisfied": not missing and not unsatisfied,
                "missing_dependencies": missing,
                "unsatisfied_dependencies": unsatisfied,
                "implementation_gate": gate,
                "implementation_authorized": canonical == authorized_canonical,
            }
        )

    active_tasks = [task["id"] for task in tasks if task["status"] == "IN_PROGRESS"]
    active_task_refs = [
        task["canonical_id"] for task in tasks if task["status"] == "IN_PROGRESS"
    ]
    ordered_candidates = [
        task
        for task in tasks
        if task["status"] == "NOT_STARTED" and task["ordered_dependency_satisfied"]
    ]
    ordered_candidate = (
        ordered_candidates[0]["canonical_id"] if len(ordered_candidates) == 1 else None
    )

    dirty_paths = porcelain_paths(repo)
    branch_result = run_git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False)
    branch = branch_result.stdout.strip() or None
    worktrees = parse_worktrees(repo)
    other_active = [
        {"path": item["path"], "active_task_refs": item["active_task_refs"]}
        for item in worktrees
        if not item["current"] and item["active_task_refs"]
    ]
    same_slice_active_elsewhere = [
        entry
        for entry in other_active
        if any(ref.startswith(f"{slice_id}-") for ref in entry["active_task_refs"])
    ]

    executable_candidates: list[str] = []
    for task in tasks:
        blockers: list[str] = []
        if task["canonical_id"] == ordered_candidate:
            blockers.extend(gate["blocking_reasons"])
            if not task["implementation_authorized"]:
                blockers.append("CURRENT_CONTEXT_IMPLEMENTATION_AUTHORIZATION_REQUIRED")
            if dirty_paths:
                blockers.append("CURRENT_WORKTREE_DIRTY")
            if active_tasks:
                blockers.append("ACTIVE_TASK_EXISTS")
            if same_slice_active_elsewhere:
                blockers.append("SAME_SLICE_ACTIVE_IN_OTHER_WORKTREE")
            task["ordered_candidate"] = True
            task["executable"] = not blockers
            if task["executable"]:
                executable_candidates.append(task["canonical_id"])
        else:
            task["ordered_candidate"] = False
            task["executable"] = False
        task["execution_blockers"] = blockers

    blocking_reasons: list[str] = []
    if len(active_tasks) > 1:
        blocking_reasons.append("MULTIPLE_IN_PROGRESS")
    if any(
        task["status"] == "IN_PROGRESS" and not task["ordered_dependency_satisfied"]
        for task in tasks
    ):
        blocking_reasons.append("ACTIVE_TASK_DEPENDENCY_UNSATISFIED")
    if any(task["missing_dependencies"] for task in tasks):
        blocking_reasons.append("UNKNOWN_DEPENDENCY")
    if not active_tasks and len(ordered_candidates) > 1:
        blocking_reasons.append("AMBIGUOUS_ORDERED_CANDIDATE")
    if dirty_paths:
        blocking_reasons.append("CURRENT_WORKTREE_DIRTY")
    if same_slice_active_elsewhere:
        blocking_reasons.append("SAME_SLICE_ACTIVE_IN_OTHER_WORKTREE")

    return {
        "ok": not blocking_reasons,
        "repository_root": str(repo),
        "head": run_git(repo, "rev-parse", "HEAD").stdout.strip(),
        "branch": branch,
        "detached": branch is None,
        "current_worktree": str(repo),
        "dirty_paths": dirty_paths,
        "tasks_file": tasks_file,
        "slice_id": slice_id,
        "policy_file": str(effective_policy_path),
        "policy_schema_version": policy.get("schema_version"),
        "tasks": tasks,
        "active_tasks": active_tasks,
        "active_task_refs": active_task_refs,
        "ordered_candidate": ordered_candidate,
        "ordered_candidates": [item["canonical_id"] for item in ordered_candidates],
        "executable_task": (
            executable_candidates[0] if len(executable_candidates) == 1 else None
        ),
        "executable_candidates": executable_candidates,
        "next_legal_task": (
            executable_candidates[0] if len(executable_candidates) == 1 else None
        ),
        "legal_next_candidates": executable_candidates,
        "implementation_authority_asserted_for": authorized_canonical,
        "human_approved_workflow_oid_asserted": approved_workflow_oid,
        "worktrees": worktrees,
        "other_dirty_worktrees": [
            item["path"]
            for item in worktrees
            if not item["current"] and item["dirty_paths"]
        ],
        "other_active_worktrees": other_active,
        "implementation_gate": gate,
        "blocking_reasons": blocking_reasons,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument(
        "--authorize-task",
        help="assert current-context implementation authority for one canonical Task",
    )
    parser.add_argument(
        "--approved-workflow-oid",
        help="assert current-context Human approval for one exact baseline commit",
    )
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = inspect(
            args.repo,
            implementation_authorized_task=args.authorize_task,
            approved_workflow_oid=args.approved_workflow_oid,
        )
    except (InspectionError, OSError, UnicodeError) as exc:
        payload = {"ok": False, "error": str(exc)}
        print(
            json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
