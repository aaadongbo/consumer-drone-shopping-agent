#!/usr/bin/env python3
"""Inspect Git/worktree and ordered Slice Task state without modifying files."""

from __future__ import annotations

import argparse
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
        dependencies = TASK_ID.findall(dependency_cell)
        tasks.append(
            {
                "id": task_id,
                "title": title,
                "status": status,
                "dependencies": dependencies,
                "dependency_text": dependency_cell,
            }
        )
    if not tasks:
        raise InspectionError(f"no Task status rows found in {path}")
    if len({task["id"] for task in tasks}) != len(tasks):
        raise InspectionError(f"duplicate Task IDs in {path}")
    return tasks


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
        dirty_paths: list[str]
        worktree_active_tasks: list[str]
        try:
            dirty_paths = porcelain_paths(path)
        except InspectionError as exc:
            dirty_paths = [f"<inspection-error: {exc}>"]
        try:
            worktree_tasks = parse_tasks(find_tasks_file(path))
            worktree_active_tasks = [
                task["id"] for task in worktree_tasks if task["status"] == "IN_PROGRESS"
            ]
        except (InspectionError, OSError, UnicodeError):
            worktree_active_tasks = []
        worktrees.append(
            {
                "path": str(path),
                "head": record.get("HEAD"),
                "branch": record.get("branch"),
                "detached": "detached" in record,
                "current": path == current_root,
                "dirty_paths": dirty_paths,
                "active_tasks": worktree_active_tasks,
            }
        )
    return worktrees


def inspect(repo_arg: str | Path = ".") -> dict[str, Any]:
    repo = repository_root(repo_arg)
    tasks_file = find_tasks_file(repo)
    tasks = parse_tasks(tasks_file)
    status_by_id = {task["id"]: task["status"] for task in tasks}

    for task in tasks:
        missing = [dep for dep in task["dependencies"] if dep not in status_by_id]
        unsatisfied = [
            dep for dep in task["dependencies"] if status_by_id.get(dep) != "DONE"
        ]
        task["dependency_satisfied"] = not missing and not unsatisfied
        task["missing_dependencies"] = missing
        task["unsatisfied_dependencies"] = unsatisfied

    active_tasks = [task["id"] for task in tasks if task["status"] == "IN_PROGRESS"]
    legal_next = [
        task["id"]
        for task in tasks
        if task["status"] == "NOT_STARTED" and task["dependency_satisfied"]
    ]
    blocking_reasons: list[str] = []
    if len(active_tasks) > 1:
        blocking_reasons.append("MULTIPLE_IN_PROGRESS")
    if any(
        task["status"] == "IN_PROGRESS" and not task["dependency_satisfied"]
        for task in tasks
    ):
        blocking_reasons.append("ACTIVE_TASK_DEPENDENCY_UNSATISFIED")
    if any(task["missing_dependencies"] for task in tasks):
        blocking_reasons.append("UNKNOWN_DEPENDENCY")
    if not active_tasks and len(legal_next) > 1:
        blocking_reasons.append("AMBIGUOUS_NEXT_TASK")
    if active_tasks and legal_next:
        blocking_reasons.append("ACTIVE_TASK_EXISTS")

    dirty_paths = porcelain_paths(repo)
    if dirty_paths:
        blocking_reasons.append("CURRENT_WORKTREE_DIRTY")

    branch_result = run_git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False)
    branch = branch_result.stdout.strip() or None
    worktrees = parse_worktrees(repo)
    other_dirty = [
        worktree["path"]
        for worktree in worktrees
        if not worktree["current"] and worktree["dirty_paths"]
    ]
    other_active = [
        {"path": worktree["path"], "active_tasks": worktree["active_tasks"]}
        for worktree in worktrees
        if not worktree["current"] and worktree["active_tasks"]
    ]
    if len(legal_next) == 1 and any(
        legal_next[0] in item["active_tasks"] for item in other_active
    ):
        blocking_reasons.append("NEXT_TASK_ACTIVE_IN_OTHER_WORKTREE")

    return {
        "ok": not blocking_reasons,
        "repository_root": str(repo),
        "head": run_git(repo, "rev-parse", "HEAD").stdout.strip(),
        "branch": branch,
        "detached": branch is None,
        "current_worktree": str(repo),
        "dirty_paths": dirty_paths,
        "tasks_file": str(tasks_file.relative_to(repo)),
        "tasks": tasks,
        "active_tasks": active_tasks,
        "next_legal_task": legal_next[0] if len(legal_next) == 1 else None,
        "legal_next_candidates": legal_next,
        "worktrees": worktrees,
        "other_dirty_worktrees": other_dirty,
        "other_active_worktrees": other_active,
        "blocking_reasons": blocking_reasons,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="pretty-print JSON instead of compact JSON",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = inspect(args.repo)
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
