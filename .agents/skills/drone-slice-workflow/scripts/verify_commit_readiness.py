#!/usr/bin/env python3
"""Read-only COMMIT_READY checks for one reviewed and Human-approved Task."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_scope import changed_paths, check
from inspect_state import InspectionError, inspect, repository_root, run_git


def normalize_task_id(task_id: str) -> str:
    return task_id.strip().upper()


def working_diff_sha256(
    repo: Path,
    task_id: str,
    head: str | None = None,
) -> str:
    """Hash Task, HEAD, and changed content; invariant only to staging."""
    normalized_task = normalize_task_id(task_id)
    base_head = head or run_git(repo, "rev-parse", "HEAD").stdout.strip()
    digest = hashlib.sha256()
    encoded_task = normalized_task.encode("ascii")
    digest.update(b"TASK_ID\0")
    digest.update(len(encoded_task).to_bytes(8, "big"))
    digest.update(encoded_task)
    encoded_head = base_head.encode("ascii")
    digest.update(b"BASE_HEAD\0")
    digest.update(len(encoded_head).to_bytes(8, "big"))
    digest.update(encoded_head)
    paths = changed_paths(repo)["all"]
    for relative in paths:
        encoded_path = relative.encode(errors="surrogateescape")
        digest.update(b"PATH\0")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        path = repo / relative
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            digest.update(b"\0DELETED\0")
            continue
        digest.update(b"\0MODE\0")
        digest.update(oct(stat.S_IMODE(metadata.st_mode)).encode("ascii"))
        if stat.S_ISLNK(metadata.st_mode):
            content = os.readlink(path).encode(errors="surrogateescape")
            digest.update(b"\0SYMLINK\0")
        elif stat.S_ISREG(metadata.st_mode):
            content = path.read_bytes()
            digest.update(b"\0FILE\0")
        else:
            content = b""
            digest.update(b"\0OTHER\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def review_snapshot(task_id: str, repo_arg: str | Path = ".") -> dict[str, Any]:
    normalized_task = normalize_task_id(task_id)
    repo = repository_root(repo_arg)
    state = inspect(repo)
    scope = check(normalized_task, repo)
    active_tasks = state["active_tasks"]
    reasons = list(scope.get("blocking_reasons", []))
    if len(active_tasks) > 1 and "MULTIPLE_IN_PROGRESS" not in reasons:
        reasons.append("MULTIPLE_IN_PROGRESS")
    if active_tasks and normalized_task not in active_tasks:
        reasons.append("DIFFERENT_ACTIVE_TASK_IN_PROGRESS")
    if "error" in scope and scope["error"] not in reasons:
        reasons.append(scope["error"])
    current_head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    return {
        "ok": not reasons,
        "repository_root": str(repo),
        "task": normalized_task,
        "actual_active_tasks": active_tasks,
        "base_head": current_head,
        "current_diff_sha256": working_diff_sha256(repo, normalized_task, current_head),
        "changed_paths": changed_paths(repo)["all"],
        "scope": scope,
        "blocking_reasons": reasons,
    }


def cached_diff_check(repo: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": "git diff --cached --check",
        "exit_code": result.returncode,
        "summary": "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        ),
    }


def verify(
    task_id: str,
    reviewed_head: str,
    reviewed_diff_sha256: str,
    repo_arg: str | Path = ".",
    *,
    ai_review_pass: bool,
    human_approved: bool,
    dependency_review_confirmed: bool = False,
) -> dict[str, Any]:
    task_id = normalize_task_id(task_id)
    repo = repository_root(repo_arg)
    state = inspect(repo)
    scope = check(task_id, repo)
    if "error" in scope:
        return scope

    paths = changed_paths(repo)
    current_head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    current_hash = working_diff_sha256(repo, task_id, current_head)
    cached_check = cached_diff_check(repo)
    task_done = scope["task_status"] == "DONE"
    all_changes_staged = (
        bool(paths["all"])
        and paths["staged"] == paths["all"]
        and not paths["unstaged"]
        and not paths["untracked"]
    )
    extra_staged = [
        path for path in paths["staged"] if path in set(scope["disallowed_paths"])
    ]
    reviewed_hash_matches = reviewed_diff_sha256.lower() == current_hash
    reviewed_head_matches = reviewed_head.lower() == current_head
    active_tasks = state["active_tasks"]
    dependency_review = scope["dependency_review"]
    dependency_confirmation_required = dependency_review["manual_confirmation_required"]

    reasons: list[str] = []
    if not task_done:
        reasons.append("TASK_NOT_DONE")
    if not ai_review_pass:
        reasons.append("AI_REVIEW_PASS_NOT_SUPPLIED")
    if not human_approved:
        reasons.append("CURRENT_CONTEXT_HUMAN_APPROVAL_NOT_SUPPLIED")
    if len(active_tasks) > 1:
        reasons.append("MULTIPLE_IN_PROGRESS")
    if active_tasks and task_id not in active_tasks:
        reasons.append("DIFFERENT_ACTIVE_TASK_IN_PROGRESS")
    if dependency_confirmation_required and not dependency_review_confirmed:
        reasons.append("DEPENDENCY_MANUAL_CONFIRMATION_REQUIRED")
    if not reviewed_head_matches:
        reasons.append("REVIEWED_HEAD_MISMATCH")
    if not reviewed_hash_matches:
        reasons.append("REVIEWED_DIFF_HASH_MISMATCH")
    if not paths["staged"]:
        reasons.append("NO_STAGED_CHANGES")
    if not all_changes_staged:
        reasons.append("NOT_ALL_CHANGES_STAGED")
    if extra_staged:
        reasons.append("EXTRA_STAGED_PATH")
    if cached_check["exit_code"] != 0:
        reasons.append("CACHED_DIFF_CHECK_FAILED")
    if not scope["ok"]:
        reasons.extend(
            reason for reason in scope["blocking_reasons"] if reason not in reasons
        )

    commit_ready = not reasons
    return {
        "ok": commit_ready,
        "repository_root": str(repo),
        "task": task_id,
        "actual_active_tasks": active_tasks,
        "task_status": scope["task_status"],
        "ai_review_evidence": {
            "pass_supplied_from_current_workflow_context": ai_review_pass,
            "reviewed_head": reviewed_head.lower(),
            "current_head": current_head,
            "head_matches": reviewed_head_matches,
            "reviewed_diff_sha256": reviewed_diff_sha256.lower(),
            "current_diff_sha256": current_hash,
            "hash_matches": reviewed_hash_matches,
        },
        "human_approval_supplied_from_current_context": human_approved,
        "dependency_review_evidence": {
            "required": dependency_confirmation_required,
            "confirmed_from_current_workflow_context": dependency_review_confirmed,
            "changed_paths": dependency_review["changed_paths"],
            "condition": dependency_review["condition"],
        },
        "changed_paths": paths["all"],
        "staged_paths": paths["staged"],
        "unstaged_paths": paths["unstaged"],
        "untracked_paths": paths["untracked"],
        "extra_staged_paths": extra_staged,
        "all_changes_staged": all_changes_staged,
        "cached_diff_check": cached_check,
        "scope": scope,
        "workflow_stage": "COMMIT_READY" if commit_ready else "HUMAN_APPROVAL_REQUIRED",
        "blocking_reasons": reasons,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Task ID, for example T06")
    parser.add_argument(
        "--reviewed-head",
        help="HEAD OID emitted by the passing AI review",
    )
    parser.add_argument(
        "--reviewed-diff-sha256",
        help="digest emitted by the passing AI review",
    )
    parser.add_argument(
        "--ai-review-pass",
        action="store_true",
        help="assert that current workflow context has AI_REVIEW_PASS",
    )
    parser.add_argument(
        "--human-approved",
        action="store_true",
        help="assert explicit local-commit approval in the current user context",
    )
    parser.add_argument(
        "--dependency-review-confirmed",
        action="store_true",
        help=(
            "assert manual review of a plan-authorized dependency diff; required only "
            "when dependency files changed"
        ),
    )
    parser.add_argument(
        "--hash-only",
        action="store_true",
        help="only print the current staging-invariant diff digest",
    )
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        repo = repository_root(args.repo)
        if args.hash_only:
            payload = review_snapshot(args.task, repo)
        elif not args.reviewed_head or not args.reviewed_diff_sha256:
            payload = {
                "ok": False,
                "task": args.task.upper(),
                "error": (
                    "--reviewed-head and --reviewed-diff-sha256 are required unless "
                    "--hash-only is used"
                ),
            }
        else:
            payload = verify(
                args.task,
                args.reviewed_head,
                args.reviewed_diff_sha256,
                repo,
                ai_review_pass=args.ai_review_pass,
                human_approved=args.human_approved,
                dependency_review_confirmed=args.dependency_review_confirmed,
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
