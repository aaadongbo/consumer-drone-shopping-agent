#!/usr/bin/env python3
"""Produce immutable review evidence; never accepts a checkpoint automatically."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_scope import RISK_RANK, changed_paths, check, check_slice_range, range_paths
from inspect_state import (
    EXPECTED_WORKFLOW_BASELINE_MARKER,
    EXPECTED_WORKFLOW_SCHEMA_VERSION,
    InspectionError,
    inspect,
    load_revision_policy,
    normalize_task_ref,
    porcelain_paths,
    protected_ref_patterns,
    protected_refs,
    repository_root,
    run_git,
)
from verify_task import verify as verify_task

WORKFLOW_POLICY_REPAIR_IDENTITIES = {
    "WORKFLOW-S03-POLICY": "changes/slice-03-target-resolution/tasks.md",
    "WORKFLOW-S04-POLICY": "changes/slice-04-variant-comparison/tasks.md",
    "WORKFLOW-S05-POLICY": "changes/slice-05-product-rag/tasks.md",
    "WORKFLOW-S08-POLICY": "changes/slice-08-data-backed-rag/tasks.md",
    "WORKFLOW-S09-POLICY": "changes/slice-09-controlled-rag-experiment/tasks.md",
}
WORKFLOW_POLICY_PRE_ACTIVATION_IDENTITIES = {"WORKFLOW-S05-POLICY"}
WORKFLOW_POLICY_REPAIR_IDENTITY = "WORKFLOW-S03-POLICY"
WORKFLOW_POLICY_REPAIR_TASKS_FILE = WORKFLOW_POLICY_REPAIR_IDENTITIES[
    WORKFLOW_POLICY_REPAIR_IDENTITY
]
WORKFLOW_POLICY_REPAIR_PATHS = {
    "AGENTS.md",
    ".agents/skills/drone-slice-workflow/SKILL.md",
    ".agents/skills/drone-slice-workflow/references/execution-protocol.md",
    ".agents/skills/drone-slice-workflow/references/review-checklist.md",
    ".agents/skills/drone-slice-workflow/references/task-scope-policy.json",
    ".agents/skills/drone-slice-workflow/scripts/check_scope.py",
    ".agents/skills/drone-slice-workflow/scripts/inspect_state.py",
    ".agents/skills/drone-slice-workflow/scripts/test_workflow_scripts.py",
    ".agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py",
    ".agents/skills/drone-slice-workflow/scripts/verify_task.py",
}
WORKFLOW_POLICY_PRE_ACTIVATION_PATHS = {
    "WORKFLOW-S05-POLICY": {
        ".agents/skills/drone-slice-workflow/references/task-scope-policy.json",
        ".agents/skills/drone-slice-workflow/scripts/check_scope.py",
        ".agents/skills/drone-slice-workflow/scripts/test_workflow_scripts.py",
        ".agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py",
    },
    "WORKFLOW-S08-POLICY": {
        ".agents/skills/drone-slice-workflow/references/task-scope-policy.json",
        ".agents/skills/drone-slice-workflow/scripts/inspect_state.py",
        ".agents/skills/drone-slice-workflow/scripts/test_workflow_scripts.py",
        ".agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py",
        "changes/slice-08-data-backed-rag/tasks.md",
    },
    "WORKFLOW-S09-POLICY": {
        ".agents/skills/drone-slice-workflow/references/task-scope-policy.json",
        ".agents/skills/drone-slice-workflow/scripts/inspect_state.py",
        ".agents/skills/drone-slice-workflow/scripts/test_workflow_scripts.py",
        ".agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py",
        "changes/slice-09-controlled-rag-experiment/tasks.md",
    },
}
WORKFLOW_POLICY_PRE_ACTIVATION_PLAN_FILES = {
    "WORKFLOW-S05-POLICY": "changes/slice-05-product-rag/plan.md",
}
REVIEW_EVIDENCE_SCHEMA_VERSION = 1


def validate_reviewer_evidence(
    payload: Any, evidence: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate a child-review JSON summary against immutable evidence."""
    reasons: list[str] = []
    if not isinstance(payload, dict):
        return None, ["REVIEWER_EVIDENCE_REQUIRED"]
    required = {
        "schema_version": REVIEW_EVIDENCE_SCHEMA_VERSION,
        "verdict": "AI_REVIEW_PASS",
        "mode": (evidence or {}).get("mode"),
        "slice": (evidence or {}).get("slice"),
        "task": (evidence or {}).get("task"),
        "base_head": (evidence or {}).get("base_head"),
        "snapshot_head": (evidence or {}).get("snapshot_head"),
        "digest": (evidence or {}).get("digest"),
        "risk_tier": ((evidence or {}).get("risk_policy") or {}).get("effective_tier")
        or ((evidence or {}).get("risk_policy") or {}).get("minimum_tier"),
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            reasons.append(f"REVIEWER_EVIDENCE_{key.upper()}_MISMATCH")
    reviewer = payload.get("reviewer")
    if (
        not isinstance(reviewer, dict)
        or not all(
            isinstance(reviewer.get(key), str) and reviewer[key].strip()
            for key in ("identity", "session")
        )
        or reviewer.get("kind") != "independent-child"
    ):
        reasons.append("REVIEWER_IDENTITY_OR_INDEPENDENCE_INVALID")
    worktree = payload.get("review_worktree")
    if (
        not isinstance(worktree, dict)
        or not all(
            worktree.get(key) is expected
            for key, expected in (("detached", True), ("clean", True))
        )
        or (
            worktree.get("head") != (evidence or {}).get("snapshot_head")
            or not isinstance(worktree.get("path"), str)
            or not worktree["path"].strip()
        )
    ):
        reasons.append("REVIEWER_WORKTREE_INVALID")
    if payload.get("no_write") is not True:
        reasons.append("REVIEWER_NO_WRITE_REQUIRED")
    if payload.get("findings") != []:
        reasons.append("REVIEWER_FINDINGS_NOT_EMPTY")
    verification = payload.get("verification")
    commands = verification.get("commands") if isinstance(verification, dict) else None
    if (
        not isinstance(commands, list)
        or not commands
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("command"), str)
            or not item["command"].strip()
            or item.get("exit_code") != 0
            or not isinstance(item.get("result"), str)
            or not item["result"].strip()
            for item in commands
        )
    ):
        reasons.append("REVIEWER_VERIFICATION_RECORD_INVALID")
    return payload, list(dict.fromkeys(reasons))


def load_reviewer_evidence(path: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    if not path:
        # The risk-tier-specific validator supplies the fail-closed required
        # reason for MEDIUM; LOW has no checkpoint review path.
        return None, []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ["REVIEWER_EVIDENCE_FILE_INVALID"]
    return payload, []


def _frame(hasher: hashlib._Hash, label: str, value: str | bytes) -> None:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    hasher.update(len(label).to_bytes(4, "big"))
    hasher.update(label.encode("utf-8"))
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def resolve_commit(repo: Path, revision: str) -> str:
    result = run_git(
        repo, "rev-parse", "--verify", f"{revision}^{{commit}}", check=False
    )
    if result.returncode != 0:
        raise InspectionError(f"invalid commit revision: {revision}")
    return result.stdout.strip()


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    return (
        run_git(
            repo, "merge-base", "--is-ancestor", older, newer, check=False
        ).returncode
        == 0
    )


def tree_entry(repo: Path, revision: str, path: str) -> dict[str, str]:
    result = run_git(repo, "ls-tree", "-z", revision, "--", path, check=False)
    if result.returncode != 0 or not result.stdout:
        return {"mode": "000000", "type": "missing", "path": path}
    record = result.stdout.split("\0", 1)[0]
    metadata, entry_path = record.split("\t", 1)
    mode, entry_type, object_id = metadata.split()
    return {"mode": mode, "type": entry_type, "oid": object_id, "path": entry_path}


def snapshot_content(repo: Path, revision: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return b""
    return result.stdout


def revision_text(repo: Path, revision: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def range_manifest(
    repo: Path, base_revision: str, snapshot_revision: str
) -> list[dict[str, Any]]:
    paths = range_paths(repo, base_revision, snapshot_revision)
    manifest: list[dict[str, Any]] = []
    for path in paths:
        entry = tree_entry(repo, snapshot_revision, path)
        content = snapshot_content(repo, snapshot_revision, path)
        file_type = {"120000": "symlink", "160000": "submodule"}.get(
            entry["mode"], entry["type"]
        )
        manifest.append(
            {
                "path": path,
                "file_type": file_type,
                "mode": entry["mode"],
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "content_size": len(content),
            }
        )
    return manifest


def commit_range_sha256(
    repo_arg: str | Path,
    base_revision: str,
    snapshot_revision: str,
    *,
    task_ref: str = "",
    mode: str = "task-review",
) -> str:
    repo = repository_root(repo_arg)
    base = resolve_commit(repo, base_revision)
    snapshot = resolve_commit(repo, snapshot_revision)
    identity = task_ref.strip().upper()
    if identity in WORKFLOW_POLICY_PRE_ACTIVATION_IDENTITIES:
        state = pre_activation_workflow_state(repo, snapshot, identity)
        canonical_task = identity
    else:
        state = inspect(repo)
        canonical_task = canonical_review_identity(task_ref, state)
    manifest = range_manifest(repo, base, snapshot)
    hasher = hashlib.sha256()
    _frame(hasher, "digest-version", "immutable-review-v2")
    _frame(hasher, "slice", state["slice_id"])
    _frame(hasher, "task", canonical_task)
    _frame(hasher, "base-head", base)
    _frame(hasher, "snapshot-head", snapshot)
    _frame(hasher, "mode", mode)
    _frame(
        hasher,
        "manifest",
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    for item in manifest:
        _frame(hasher, "path", item["path"])
        _frame(hasher, "file-type", item["file_type"])
        _frame(hasher, "file-mode", item["mode"])
        _frame(hasher, "contents", snapshot_content(repo, snapshot, item["path"]))
    return hasher.hexdigest()


def canonical_review_identity(task_ref: str, state: dict[str, Any]) -> str:
    identity = (task_ref or state["slice_id"] + "-T00").strip().upper()
    if identity in WORKFLOW_POLICY_REPAIR_IDENTITIES:
        tasks_file = WORKFLOW_POLICY_REPAIR_IDENTITIES[identity]
        if state["tasks_file"] != tasks_file:
            raise InspectionError(f"{identity} requires active {tasks_file}")
        return identity
    _, canonical_task = normalize_task_ref(identity, state["slice_id"])
    return canonical_task


def s05_planned_nonexecutable(
    repo: Path, revision: str, identity: str
) -> tuple[dict[str, Any], list[str]]:
    tasks_file = WORKFLOW_POLICY_REPAIR_IDENTITIES[identity]
    plan_file = WORKFLOW_POLICY_PRE_ACTIVATION_PLAN_FILES[identity]
    tasks_text = revision_text(repo, revision, tasks_file)
    plan_text = revision_text(repo, revision, plan_file)
    reasons: list[str] = []
    if plan_text is None:
        reasons.append("PRE_ACTIVATION_PLAN_FILE_MISSING")
    if tasks_text is None:
        reasons.append("PRE_ACTIVATION_TASKS_FILE_MISSING")
        tasks_text = ""
    planned_ids = [f"T{number:02d}" for number in range(1, 8)]
    if "| Planned Task | Title | Planned state | Dependencies |" not in tasks_text:
        reasons.append("PRE_ACTIVATION_PLANNED_TABLE_MISSING")
    if "| Task | Title | Status | Dependencies |" in tasks_text:
        reasons.append("PRE_ACTIVATION_FORMAL_TASK_TABLE_PRESENT")
    missing_planned = [
        task_id
        for task_id in planned_ids
        if f"| {task_id} |" not in tasks_text or "| PLANNED |" not in tasks_text
    ]
    if missing_planned:
        reasons.append("PRE_ACTIVATION_PLANNED_ROWS_INCOMPLETE")
    return {
        "plan_file": plan_file,
        "tasks_file": tasks_file,
        "planned_task_ids": planned_ids,
        "missing_planned_task_ids": missing_planned,
        "formal_task_table_present": "| Task | Title | Status | Dependencies |"
        in tasks_text,
    }, reasons


def pre_activation_workflow_state(
    repo: Path, revision: str, identity: str
) -> dict[str, Any]:
    tasks_file = WORKFLOW_POLICY_REPAIR_IDENTITIES[identity]
    return {
        "repository_root": str(repo),
        "slice_id": "S05",
        "tasks_file": tasks_file,
        "tasks": [],
        "other_active_worktrees": [],
        "pre_activation": True,
        "pre_activation_revision": revision,
    }


def workflow_policy_allowed_paths(identity: str) -> set[str]:
    return WORKFLOW_POLICY_PRE_ACTIVATION_PATHS.get(
        identity, WORKFLOW_POLICY_REPAIR_PATHS
    )


def workflow_policy_repair_scope(
    repo: Path,
    state: dict[str, Any],
    base: str,
    snapshot: str,
    identity: str = WORKFLOW_POLICY_REPAIR_IDENTITY,
) -> dict[str, Any]:
    paths = range_paths(repo, base, snapshot)
    allowed_paths = workflow_policy_allowed_paths(identity)
    disallowed = [path for path in paths if path not in allowed_paths]
    tasks_file = WORKFLOW_POLICY_REPAIR_IDENTITIES[identity]
    reasons: list[str] = []
    pre_activation = identity in WORKFLOW_POLICY_PRE_ACTIVATION_IDENTITIES
    planned_state: dict[str, Any] | None = None
    if pre_activation:
        planned_state, planned_reasons = s05_planned_nonexecutable(
            repo, snapshot, identity
        )
        reasons.extend(planned_reasons)
    elif state["tasks_file"] != tasks_file:
        reasons.append("WORKFLOW_POLICY_IDENTITY_SLICE_MISMATCH")
    else:
        s05_allowed_paths = WORKFLOW_POLICY_PRE_ACTIVATION_PATHS["WORKFLOW-S05-POLICY"]
        s05_planned_state, s05_planned_reasons = s05_planned_nonexecutable(
            repo, snapshot, "WORKFLOW-S05-POLICY"
        )
        if (
            not s05_planned_reasons
            and set(paths).issubset(s05_allowed_paths)
            and s05_planned_state["tasks_file"] != tasks_file
        ):
            reasons.append("WORKFLOW_POLICY_IDENTITY_SLICE_MISMATCH")
    if not paths:
        reasons.append("NO_WORKFLOW_POLICY_CHANGES")
    if disallowed:
        reasons.append("PATH_OUTSIDE_WORKFLOW_POLICY_SCOPE")
    return {
        "ok": not reasons,
        "scope_kind": "workflow-policy",
        "repository_root": str(repo),
        "active_slice_tasks_file": state["tasks_file"],
        "slice": state["slice_id"],
        "task": identity,
        "local_task": None,
        "pre_activation": pre_activation,
        "planned_nonexecutable": planned_state,
        "immutable_range": True,
        "base_head": base,
        "snapshot_head": snapshot,
        "allowed_patterns": sorted(allowed_paths),
        "changed_paths": paths,
        "staged_paths": [],
        "unstaged_paths": [],
        "untracked_paths": [],
        "disallowed_paths": disallowed,
        "core_artifact_changes": [],
        "dependency_review": {
            "mode": "workflow-policy-repair-only",
            "changed_paths": [],
            "allowed_by_task_policy": False,
            "manual_confirmation_required": False,
            "condition": (
                "Only explicit workflow policy repair identities may change "
                "the predefined workflow policy files."
            ),
        },
        "forbidden_slice_path_changes": [],
        "risk_policy": {
            "minimum_tier": "HIGH",
            "effective_tier": "HIGH",
            "checkpoint_policy": "human-decision",
            "automation": {
                "auto_advance": False,
                "human_gate": "task",
                "review_required": True,
                "verification_mode": "workflow-policy-repair",
            },
            "deterministic_escalation_paths": [],
            "semantic_review_required": True,
            "human_decision_required": True,
        },
        "blocking_reasons": reasons,
    }


def public_manifest(repo: Path, base: str, snapshot: str) -> list[dict[str, Any]]:
    return range_manifest(repo, base, snapshot)


def protected_ref_heads(repo: Path, policy: dict[str, Any]) -> dict[str, str]:
    heads: dict[str, str] = {}
    for ref in protected_refs(repo, policy):
        heads[ref] = resolve_commit(repo, ref)
    return heads


def immutable_evidence(
    task_ref: str,
    base_revision: str,
    snapshot_revision: str,
    repo_arg: str | Path = ".",
    *,
    mode: str = "task-review",
) -> dict[str, Any]:
    repo = repository_root(repo_arg)
    requested_identity = task_ref.strip().upper()
    workflow_policy_repair = requested_identity in WORKFLOW_POLICY_REPAIR_IDENTITIES
    workflow_policy_pre_activation = (
        requested_identity in WORKFLOW_POLICY_PRE_ACTIVATION_IDENTITIES
    )
    base = resolve_commit(repo, base_revision)
    snapshot = resolve_commit(repo, snapshot_revision)
    if workflow_policy_pre_activation:
        state = pre_activation_workflow_state(repo, snapshot, requested_identity)
    else:
        state = inspect(repo)
    if workflow_policy_repair:
        local_task, canonical_task = None, requested_identity
    else:
        local_task, canonical_task = normalize_task_ref(task_ref, state["slice_id"])
    current = resolve_commit(repo, "HEAD")
    policy, policy_error = load_revision_policy(repo, snapshot)
    policy = policy or {}
    blockers: list[str] = []
    if policy_error:
        blockers.append(policy_error)
    if policy.get("schema_version") != EXPECTED_WORKFLOW_SCHEMA_VERSION:
        blockers.append("SNAPSHOT_POLICY_SCHEMA_MISMATCH")
    if policy.get("workflow_baseline_marker") != EXPECTED_WORKFLOW_BASELINE_MARKER:
        blockers.append("SNAPSHOT_POLICY_MARKER_MISMATCH")
    if current != snapshot:
        blockers.append("SNAPSHOT_HEAD_NOT_CHECKED_OUT")
    if not is_ancestor(repo, base, snapshot):
        blockers.append("SNAPSHOT_BASE_NOT_ANCESTOR")
    changed = range_paths(repo, base, snapshot)
    if not changed:
        blockers.append("SNAPSHOT_RANGE_EMPTY")
    dirty = porcelain_paths(repo)
    if dirty:
        blockers.append("SNAPSHOT_WORKTREE_DIRTY")
    task = (
        None
        if workflow_policy_repair
        else next((item for item in state["tasks"] if item["id"] == local_task), None)
    )
    if task is None and not workflow_policy_repair:
        blockers.append("ILLEGAL_OR_UNKNOWN_TASK_ID")
    if mode not in {"task-review", "slice-review"}:
        blockers.append("INVALID_REVIEW_MODE")
    if workflow_policy_repair and mode != "task-review":
        scope = workflow_policy_repair_scope(
            repo, state, base, snapshot, canonical_task
        )
        blockers.append("INVALID_WORKFLOW_POLICY_REVIEW_MODE")
    elif workflow_policy_repair:
        scope = workflow_policy_repair_scope(
            repo, state, base, snapshot, canonical_task
        )
    elif mode == "slice-review":
        scope = check_slice_range(
            canonical_task,
            repo,
            base_head=base,
            snapshot_head=snapshot,
        )
    else:
        scope = check(canonical_task, repo, base_head=base, snapshot_head=snapshot)
        if task is not None and task["status"] != "DONE":
            blockers.append("TASK_NOT_DONE")
    blockers.extend(scope.get("blocking_reasons", []))
    other_slice_active = [
        item
        for item in state.get("other_active_worktrees", [])
        if any(
            ref.startswith(f"{state['slice_id']}-")
            for ref in item.get("active_task_refs", [])
        )
    ]
    if other_slice_active:
        blockers.append("SAME_SLICE_ACTIVE_IN_OTHER_WORKTREE")
    ref_heads = protected_ref_heads(repo, policy) if policy else {}
    snapshot_protected_refs = sorted(
        ref for ref, oid in ref_heads.items() if oid == snapshot
    )
    if snapshot_protected_refs:
        blockers.append("SNAPSHOT_ON_PROTECTED_BRANCH")
    branch = (
        run_git(
            repo, "symbolic-ref", "--short", "-q", "HEAD", check=False
        ).stdout.strip()
        or None
    )
    if branch:
        full_ref = f"refs/heads/{branch}"
        if full_ref in ref_heads and current == snapshot:
            blockers.append("SNAPSHOT_ON_PROTECTED_BRANCH")
    digest = commit_range_sha256(
        repo, base, snapshot, task_ref=canonical_task, mode=mode
    )
    return {
        "ok": not blockers,
        "workflow_stage": "IMMUTABLE_REVIEW_EVIDENCE" if not blockers else "BLOCKED",
        "repository_root": str(repo),
        "slice": state["slice_id"],
        "task": canonical_task,
        "local_task": local_task,
        "mode": mode,
        "base_head": base,
        "snapshot_head": snapshot,
        "current_head": current,
        "branch": branch,
        "detached": branch is None,
        "dirty_paths": dirty,
        "changed_paths": changed,
        "manifest": public_manifest(repo, base, snapshot),
        "digest": digest,
        "scope": scope,
        "risk_policy": scope.get("risk_policy"),
        "protected_ref_patterns": protected_ref_patterns(policy) if policy else [],
        "protected_refs_at_snapshot": snapshot_protected_refs,
        "integration_authorized": False,
        "push_authorized": False,
        "human_approval": False,
        "blocking_reasons": list(dict.fromkeys(blockers)),
    }


def working_diff_sha256(
    repo_arg: str | Path = ".", task_ref: str | None = None, head: str | None = None
) -> str:
    repo = repository_root(repo_arg)
    result = run_git(repo, "diff", "--binary", "HEAD", check=False)
    staged = run_git(repo, "diff", "--binary", "--cached", check=False)
    untracked = "\n".join(porcelain_paths(repo))
    hasher = hashlib.sha256()
    _frame(hasher, "digest-version", "working-tree-v1")
    _frame(hasher, "head", resolve_commit(repo, head or "HEAD"))
    if task_ref:
        _frame(hasher, "task", task_ref.strip().upper())
    _frame(hasher, "unstaged", result.stdout)
    _frame(hasher, "staged", staged.stdout)
    _frame(hasher, "paths", untracked)
    return hasher.hexdigest()


def review_snapshot(
    task_or_repo: str | Path = ".", repo_arg: str | Path | None = None
) -> dict[str, Any]:
    task_ref = None if repo_arg is None else str(task_or_repo)
    repo = repository_root(repo_arg if repo_arg is not None else task_or_repo)
    digest = working_diff_sha256(repo, task_ref)
    current_head = resolve_commit(repo, "HEAD")
    changed = changed_paths(repo)["all"]
    return {
        "ok": True,
        "workflow_stage": "LEGACY_WORKING_TREE_REVIEW",
        "mode": "legacy-working-tree",
        "compatibility_only": True,
        "checkpoint_eligible": False,
        "task": task_ref.upper() if task_ref else None,
        "base_head": current_head,
        "changed_paths": changed,
        "digest": digest,
        "current_diff_sha256": digest,
        "integration_authorized": False,
        "push_authorized": False,
        "human_approval": False,
    }


def verify(
    task_ref: str,
    reviewed_head: str,
    reviewed_digest: str,
    repo_arg: str | Path = ".",
    human_approved: bool = False,
    dependency_review_confirmed: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper; legacy working-tree verification cannot accept."""
    return checkpoint_readiness(
        task_ref,
        repo_arg,
        base_revision=reviewed_head,
        snapshot_revision=reviewed_head,
        reviewed_digest=reviewed_digest,
        human_approved=human_approved,
        dependency_review_confirmed=dependency_review_confirmed,
    )


def checkpoint_readiness(
    task_ref: str,
    repo_arg: str | Path = ".",
    *,
    base_revision: str | None = None,
    snapshot_revision: str | None = None,
    reviewed_digest: str | None = None,
    mode: str = "task-review",
    verification_pass: bool = False,
    reviewed_risk_tier: str | None = None,
    reviewer_evidence: dict[str, Any] | None = None,
    human_approved: bool = False,
    dependency_review_confirmed: bool = False,
) -> dict[str, Any]:
    evidence: dict[str, Any] | None = None
    readiness_blockers: list[str] = []
    if not (base_revision and snapshot_revision):
        readiness_blockers.append("IMMUTABLE_BASE_AND_SNAPSHOT_REQUIRED")
    else:
        try:
            evidence = immutable_evidence(
                task_ref,
                base_revision,
                snapshot_revision,
                repo_arg,
                mode=mode,
            )
            readiness_blockers.extend(evidence.get("blocking_reasons", []))
        except (InspectionError, OSError, UnicodeError) as exc:
            readiness_blockers.append(f"EVIDENCE_ERROR:{exc}")
    digest_matches = bool(
        evidence and reviewed_digest and reviewed_digest == evidence["digest"]
    )
    if not reviewed_digest:
        readiness_blockers.append("REVIEWED_DIGEST_REQUIRED")
    elif not digest_matches:
        readiness_blockers.append("REVIEWED_DIGEST_MISMATCH")
    if reviewed_risk_tier is None:
        readiness_blockers.append("REVIEWED_RISK_TIER_REQUIRED")
    elif reviewed_risk_tier not in RISK_RANK:
        readiness_blockers.append("REVIEWED_RISK_TIER_INVALID")
    elif evidence:
        risk_policy = evidence.get("risk_policy") or {}
        required_tier = risk_policy.get("effective_tier") or risk_policy.get(
            "minimum_tier"
        )
        if required_tier in RISK_RANK and (
            RISK_RANK[reviewed_risk_tier] < RISK_RANK[required_tier]
        ):
            readiness_blockers.append("REVIEWED_RISK_TIER_BELOW_POLICY_MINIMUM")
    dependency_review = (evidence or {}).get("scope", {}).get("dependency_review", {})
    risk_policy = (evidence or {}).get("risk_policy") or {}
    policy_tier = risk_policy.get("effective_tier") or risk_policy.get("minimum_tier")
    reviewer_payload: dict[str, Any] | None = None
    if policy_tier == "MEDIUM":
        reviewer_payload, reviewer_reasons = validate_reviewer_evidence(
            reviewer_evidence, evidence
        )
        readiness_blockers.extend(reviewer_reasons)
    if (
        dependency_review.get("manual_confirmation_required")
        and not dependency_review_confirmed
    ):
        readiness_blockers.append("DEPENDENCY_MANUAL_CONFIRMATION_REQUIRED")

    verification: dict[str, Any] | None = None
    if evidence and digest_matches and not readiness_blockers:
        risk_policy = evidence.get("risk_policy") or {}
        boundary_full_verification = bool(
            mode == "slice-review"
            or risk_policy.get("deterministic_escalation_paths")
            or dependency_review.get("changed_paths")
        )
        verification = verify_task(
            task_ref,
            repo_arg,
            full=boundary_full_verification,
            base_head=evidence["base_head"],
            snapshot_head=evidence["snapshot_head"],
            slice_review=mode == "slice-review",
        )
        verification_results = verification.get("results") or []
        verification_bound = (
            verification.get("task") == evidence["task"]
            and verification.get("base_head") == evidence["base_head"]
            and verification.get("snapshot_head") == evidence["snapshot_head"]
            and verification.get("verification_complete") is True
            and bool(verification_results)
            and all(item.get("exit_code") == 0 for item in verification_results)
        )
        if not verification.get("ok") or not verification_bound:
            readiness_blockers.append("TARGETED_VERIFICATION_FAILED")
    elif evidence and digest_matches:
        readiness_blockers.append("TARGETED_VERIFICATION_EVIDENCE_REQUIRED")

    automation = risk_policy.get("automation") or {}
    reviewed_effective_tier = max(
        (tier for tier in (policy_tier, reviewed_risk_tier) if tier in RISK_RANK),
        key=RISK_RANK.__getitem__,
        default=None,
    )
    auto_advance = bool(
        not readiness_blockers
        and automation.get("auto_advance") is True
        and automation.get("human_gate") == "unplanned-exception"
        and reviewed_effective_tier == policy_tier
        and not risk_policy.get("deterministic_escalation_paths")
        and policy_tier != "HIGH"
    )
    ready_for_human = bool(not readiness_blockers and not auto_advance)
    workflow_stage = (
        "AUTO_ADVANCE_ELIGIBLE"
        if auto_advance
        else "HUMAN_APPROVAL_REQUIRED"
        if ready_for_human
        else "BLOCKED"
    )
    status = (
        "AUTO_ADVANCE_ELIGIBLE"
        if auto_advance
        else "HUMAN_DECISION_REQUIRED"
        if ready_for_human
        else "CHECKPOINT_NOT_READY"
    )
    reason = (
        "PLANNED_TASK_AI_REVIEW_ADVANCE_ALLOWED"
        if auto_advance
        else "HIGH_RISK_OR_UNPLANNED_ESCALATION"
        if ready_for_human
        else "CHECKPOINT_EVIDENCE_INVALID"
    )
    blockers = list(readiness_blockers)
    if ready_for_human:
        blockers.append(
            "HIGH_RISK_HUMAN_DECISION_REQUIRED"
            if policy_tier == "HIGH"
            else "UNPLANNED_ESCALATION_OR_EXCEPTION"
        )
    return {
        # Routing eligibility never accepts a checkpoint or authorizes delivery.
        "ok": auto_advance,
        "workflow_stage": workflow_stage,
        "reason": reason,
        "status": status,
        "task": task_ref.upper(),
        "mode": mode,
        "human_approval_required": ready_for_human,
        "human_approval_supplied": human_approved,
        "reviewer_evidence": reviewer_payload,
        "verification_pass_claim_ignored": verification_pass,
        "caller_verification_pass_claim_ignored": verification_pass,
        "dependency_review_confirmed": dependency_review_confirmed,
        "reviewed_risk_tier": reviewed_risk_tier,
        "reviewed_effective_tier": reviewed_effective_tier,
        "reviewed_digest": reviewed_digest,
        "digest_matches": digest_matches,
        "ready_for_human_approval": ready_for_human,
        "auto_advance": auto_advance,
        "checkpoint_accepted": False,
        "human_approval": False,
        "integration_authorized": False,
        "push_authorized": False,
        "evidence": evidence,
        "verification": verification,
        "blocking_reasons": list(dict.fromkeys(blockers)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", nargs="?", help="Task ID, for example S02-T03 or T03")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--evidence", action="store_true", help="emit immutable review evidence"
    )
    modes.add_argument(
        "--checkpoint",
        action="store_true",
        help="evaluate a policy checkpoint; never accepts or integrates",
    )
    modes.add_argument(
        "--hash-only", action="store_true", help="emit legacy working-tree digest"
    )
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    parser.add_argument("--base-head", help="immutable range base commit")
    parser.add_argument("--snapshot-head", help="immutable range snapshot commit")
    parser.add_argument("--reviewed-digest")
    parser.add_argument(
        "--mode", default="task-review", choices=["task-review", "slice-review"]
    )
    parser.add_argument(
        "--review-evidence",
        help="path to independent-child reviewer JSON (required for MEDIUM)",
    )
    parser.add_argument(
        "--verification-pass", action="store_true", help="deprecated claim; ignored"
    )
    parser.add_argument("--risk-tier", choices=["LOW", "MEDIUM", "HIGH"])
    parser.add_argument("--human-approved", action="store_true")
    parser.add_argument("--dependency-review-confirmed", action="store_true")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.hash_only:
            payload = review_snapshot(args.repo)
        elif args.checkpoint:
            reviewer_evidence, reviewer_load_reasons = load_reviewer_evidence(
                args.review_evidence
            )
            payload = checkpoint_readiness(
                args.task or "UNKNOWN",
                args.repo,
                base_revision=args.base_head,
                snapshot_revision=args.snapshot_head,
                reviewed_digest=args.reviewed_digest,
                mode=args.mode,
                verification_pass=args.verification_pass,
                reviewed_risk_tier=args.risk_tier,
                human_approved=args.human_approved,
                dependency_review_confirmed=args.dependency_review_confirmed,
                reviewer_evidence=reviewer_evidence,
            )
            if reviewer_load_reasons:
                payload["blocking_reasons"] = list(
                    dict.fromkeys(payload["blocking_reasons"] + reviewer_load_reasons)
                )
                payload["ok"] = False
                payload["workflow_stage"] = "BLOCKED"
                payload["status"] = "CHECKPOINT_NOT_READY"
        elif args.evidence:
            if not args.task or not args.base_head or not args.snapshot_head:
                raise InspectionError(
                    "--evidence requires task, --base-head, and --snapshot-head"
                )
            payload = immutable_evidence(
                args.task,
                args.base_head,
                args.snapshot_head,
                args.repo,
                mode=args.mode,
            )
        else:
            reviewer_evidence, reviewer_load_reasons = load_reviewer_evidence(
                args.review_evidence
            )
            if not args.task:
                raise InspectionError("task is required")
            payload = checkpoint_readiness(
                args.task,
                args.repo,
                base_revision=args.base_head,
                snapshot_revision=args.snapshot_head,
                reviewed_digest=args.reviewed_digest,
                mode=args.mode,
                verification_pass=args.verification_pass,
                reviewed_risk_tier=args.risk_tier,
                human_approved=args.human_approved,
                dependency_review_confirmed=args.dependency_review_confirmed,
                reviewer_evidence=reviewer_evidence,
            )
            if reviewer_load_reasons:
                payload["blocking_reasons"] = list(
                    dict.fromkeys(payload["blocking_reasons"] + reviewer_load_reasons)
                )
                payload["ok"] = False
                payload["workflow_stage"] = "BLOCKED"
                payload["status"] = "CHECKPOINT_NOT_READY"
    except (InspectionError, OSError, UnicodeError) as exc:
        payload = {"ok": False, "workflow_stage": "BLOCKED", "error": str(exc)}
        print(
            json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
