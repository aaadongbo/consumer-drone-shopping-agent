#!/usr/bin/env python3
"""Standard-library regression tests for the minimum-safe Slice workflow."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_scope import POLICY_PATH, check
from inspect_state import inspect
from verify_commit_readiness import (
    checkpoint_readiness,
    commit_range_sha256,
    immutable_evidence,
    review_snapshot,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
VERIFY_COMMIT_SCRIPT = Path(__file__).resolve().parent / "verify_commit_readiness.py"

SLICE_1_TITLES = {
    f"T{i:02d}": title
    for i, title in enumerate(
        [
            "Bootstrap",
            "Contracts",
            "Read fixture",
            "Walking skeleton",
            "Identity",
            "Fallback",
            "Scope guards",
            "Thin API",
            "Closure",
        ],
        1,
    )
}
SLICE_1_DEPENDENCIES = {
    "T01": "SATISFIED",
    "T02": "T01",
    "T03": "T02",
    "T04": "T03",
    "T05": "T04",
    "T06": "T04, T05",
    "T07": "T04, T05, T06",
    "T08": "T07",
    "T09": "T08",
}
SLICE_2_TITLES = {
    "T01": "Catalog fixture",
    "T02": "ConstraintPatch",
    "T03": "HARD eligibility",
    "T04": "SOFT baseline",
    "T05": "Recommendation contract",
    "T06": "Walking skeleton",
    "T07": "Completion evidence",
}
SLICE_2_DEPENDENCIES = {
    "T01": "Slice 1 closed; Slice 2 plan approved; Workflow Simplification baseline",
    "T02": "T01",
    "T03": "T02",
    "T04": "T03",
    "T05": "T03, T04",
    "T06": "T05",
    "T07": "T06",
}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def status_map(task_ids: list[str], done_through: str | None = None) -> dict[str, str]:
    done_number = int(done_through[1:]) if done_through else 0
    return {
        task_id: "DONE" if int(task_id[1:]) <= done_number else "NOT_STARTED"
        for task_id in task_ids
    }


def task_table(
    titles: dict[str, str], dependencies: dict[str, str], statuses: dict[str, str]
) -> str:
    rows = ["| Task | Title | Status | Dependencies |", "|---|---|---|---|"]
    rows.extend(
        f"| {task_id} | {titles[task_id]} | {statuses[task_id]} | "
        f"{dependencies[task_id]} |"
        for task_id in titles
    )
    return "\n".join(rows) + "\n"


class TemporaryRepository:
    def __init__(
        self,
        root: Path,
        *,
        slice_name: str = "slice-02-single-turn-recommendation",
        current_policy_at_head: bool = True,
    ) -> None:
        self.root = root
        self.slice_name = slice_name
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "Workflow Test")
        git(root, "config", "user.email", "workflow-test@example.invalid")
        if slice_name == "slice-01-product-facts":
            self.titles, self.dependencies = SLICE_1_TITLES, SLICE_1_DEPENDENCIES
        else:
            self.titles, self.dependencies = SLICE_2_TITLES, SLICE_2_DEPENDENCIES
        self.write_tasks(status_map(list(self.titles)))
        policy_target = (
            root
            / ".agents/skills/drone-slice-workflow/references/task-scope-policy.json"
        )
        policy_target.parent.mkdir(parents=True)
        if current_policy_at_head:
            shutil.copy2(POLICY_PATH, policy_target)
        else:
            policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            policy["schema_version"] = 1
            policy.pop("workflow_baseline_marker", None)
            policy_target.write_text(json.dumps(policy), encoding="utf-8")
        for directory in (
            "backend/catalog",
            "backend/conversation",
            "backend/evidence",
            "backend/common",
            "backend/application",
        ):
            (root / directory).mkdir(parents=True, exist_ok=True)
        for path in (
            "backend/catalog/value.py",
            "backend/conversation/value.py",
            "backend/evidence/value.py",
            "backend/application/value.py",
            "backend/common/contracts.py",
        ):
            (root / path).write_text('VALUE = "base"\n', encoding="utf-8")
        for name in ("pyproject.toml", "uv.lock", ".python-version", ".gitignore"):
            shutil.copy2(REPOSITORY_ROOT / name, root / name)
        smoke = root / "tests/unit/test_workflow_fixture.py"
        smoke.parent.mkdir(parents=True, exist_ok=True)
        smoke.write_text(
            "import pytest\n\n@pytest.mark.unit\ndef test_fixture():\n"
            "    assert True\n",
            encoding="utf-8",
        )
        git(root, "add", ".")
        git(root, "commit", "-qm", "initial")
        if not current_policy_at_head:
            shutil.copy2(POLICY_PATH, policy_target)
        git(root, "switch", "-qc", "task/test")

    @property
    def tasks_path(self) -> Path:
        return self.root / "changes" / self.slice_name / "tasks.md"

    def write_tasks(self, statuses: dict[str, str]) -> None:
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks_path.write_text(
            task_table(self.titles, self.dependencies, statuses), encoding="utf-8"
        )

    def snapshot(
        self,
        task_id: str = "T01",
        *,
        changed_path: str = "backend/catalog/change.py",
        content: str = "VALUE = 1\n",
        extra_path: str | None = None,
    ) -> tuple[str, str]:
        base = git(self.root, "rev-parse", "HEAD")
        self.write_tasks(status_map(list(self.titles), task_id))
        path = self.root / changed_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if extra_path:
            extra = self.root / extra_path
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text("extra\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", f"wip({task_id}): snapshot")
        return base, git(self.root, "rev-parse", "HEAD")


class WorkflowScriptTests(unittest.TestCase):
    def repo(
        self, **kwargs: object
    ) -> tuple[tempfile.TemporaryDirectory[str], TemporaryRepository]:
        holder = tempfile.TemporaryDirectory()
        return holder, TemporaryRepository(Path(holder.name), **kwargs)

    def test_main_snapshot_is_rejected(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        git(repo.root, "switch", "main")
        base, snapshot = repo.snapshot()
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        self.assertIn("SNAPSHOT_ON_PROTECTED_BRANCH", evidence["blocking_reasons"])

    def test_master_snapshot_is_rejected(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        git(repo.root, "branch", "master")
        git(repo.root, "switch", "master")
        base, snapshot = repo.snapshot()
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        self.assertIn("SNAPSHOT_ON_PROTECTED_BRANCH", evidence["blocking_reasons"])

    def test_detached_task_snapshot_is_valid(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        self.assertTrue(evidence["ok"], evidence)
        self.assertFalse(evidence["integration_authorized"])
        self.assertFalse(evidence["push_authorized"])

    def test_in_progress_task_review_fails_closed(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        statuses = status_map(list(repo.titles))
        statuses["T01"] = "IN_PROGRESS"
        repo.write_tasks(statuses)
        (repo.root / "backend/catalog/change.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(T01): incomplete snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)

        self.assertFalse(evidence["ok"])
        self.assertIn("TASK_NOT_DONE", evidence["blocking_reasons"])

    def test_slice_review_accepts_multi_task_scope_and_aggregates_high_risk(
        self,
    ) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        changes = {
            "backend/catalog/change.py": "CATALOG = 1\n",
            "backend/conversation/change.py": "CONVERSATION = 1\n",
            "backend/evidence/change.py": "EVIDENCE = 1\n",
        }
        for relative, content in changes.items():
            (repo.root / relative).write_text(content, encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S02): complete slice snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S02-T07", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertTrue(evidence["ok"], evidence)
        self.assertNotIn("PATH_OUTSIDE_TASK_SCOPE", evidence["blocking_reasons"])
        self.assertEqual(evidence["scope"]["scope_kind"], "slice-range")
        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "HIGH")

        wrong_task = immutable_evidence(
            "S02-T01", base, snapshot, repo.root, mode="slice-review"
        )
        self.assertFalse(wrong_task["ok"])
        self.assertIn(
            "SLICE_REVIEW_TASK_IDENTITY_MISMATCH",
            wrong_task["blocking_reasons"],
        )

    def test_slice_review_retains_core_dependency_and_forbidden_gates(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        guarded_changes = {
            "changes/slice-02-single-turn-recommendation/plan.md": "changed\n",
            "pyproject.toml": "changed\n",
            "backend/rag/forbidden.py": "FORBIDDEN = True\n",
        }
        for relative, content in guarded_changes.items():
            path = repo.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S02): invalid slice snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S02-T07", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertFalse(evidence["ok"])
        self.assertIn("CORE_ARTIFACT_CHANGED", evidence["blocking_reasons"])
        self.assertIn(
            "DEPENDENCY_FILE_CHANGED_WITHOUT_SLICE_POLICY",
            evidence["blocking_reasons"],
        )
        self.assertIn("FORBIDDEN_SLICE_PATH_CHANGED", evidence["blocking_reasons"])

    def test_slice_review_requires_every_task_done(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(task_id="T06")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S02-T07", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertFalse(evidence["ok"])
        self.assertIn("SLICE_NOT_COMPLETE", evidence["blocking_reasons"])

    def test_digest_binds_identity_mode_paths_metadata_and_contents(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(content="VALUE = 1\n")
        first = commit_range_sha256(
            repo.root, base, snapshot, task_ref="S02-T01", mode="task-review"
        )
        self.assertNotEqual(
            first,
            commit_range_sha256(
                repo.root, base, snapshot, task_ref="S02-T02", mode="task-review"
            ),
        )
        self.assertNotEqual(
            first,
            commit_range_sha256(
                repo.root, base, snapshot, task_ref="S02-T01", mode="slice-review"
            ),
        )
        base2, snapshot2 = repo.snapshot(content="VALUE = 2\n")
        self.assertNotEqual(
            first, commit_range_sha256(repo.root, base2, snapshot2, task_ref="S02-T01")
        )

    def test_digest_binds_file_mode(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "update-index", "--chmod=+x", "backend/catalog/change.py")
        git(repo.root, "commit", "-qm", "mode change")
        mode_snapshot = git(repo.root, "rev-parse", "HEAD")
        self.assertNotEqual(
            commit_range_sha256(repo.root, base, snapshot, task_ref="S02-T01"),
            commit_range_sha256(repo.root, snapshot, mode_snapshot, task_ref="S02-T01"),
        )

    def test_mutated_head_digest_and_scope_are_rejected(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(extra_path="backend/conversation/outside.py")
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        self.assertFalse(evidence["ok"])
        self.assertIn("PATH_OUTSIDE_TASK_SCOPE", evidence["blocking_reasons"])
        with self.assertRaises(Exception):
            immutable_evidence("S01-T01", base, snapshot, repo.root)

    def test_wrong_task_and_current_head_are_rejected(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        wrong_task = immutable_evidence("S02-T02", base, snapshot, repo.root)
        self.assertFalse(wrong_task["ok"])
        git(repo.root, "switch", "--detach", base)
        moved = immutable_evidence("S02-T01", base, snapshot, repo.root)
        self.assertIn("SNAPSHOT_HEAD_NOT_CHECKED_OUT", moved["blocking_reasons"])

    def test_verification_pass_claim_cannot_accept(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        result = checkpoint_readiness(
            "S02-T01",
            repo.root,
            base_revision=base,
            snapshot_revision=snapshot,
            reviewed_digest=evidence["digest"],
            ai_review_pass=True,
            verification_pass=True,
            reviewed_risk_tier="LOW",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["workflow_stage"], "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(result["reason"], "AUTOMATIC_CHECKPOINT_ACCEPTANCE_DISABLED")
        self.assertFalse(result["integration_authorized"])
        self.assertFalse(result["push_authorized"])

    def test_low_medium_review_never_auto_accepted_and_high_needs_human(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        for tier in ("LOW", "MEDIUM", "HIGH"):
            result = checkpoint_readiness(
                "S02-T01",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                ai_review_pass=True,
                reviewed_risk_tier=tier,
            )
            self.assertFalse(result["ok"])
            self.assertTrue(result["human_approval_required"])

    def test_high_risk_requires_explicit_human(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(
            task_id="T05", changed_path="backend/evidence/change.py"
        )
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T05", base, snapshot, repo.root)
        result = checkpoint_readiness(
            "S02-T05",
            repo.root,
            base_revision=base,
            snapshot_revision=snapshot,
            reviewed_digest=evidence["digest"],
            ai_review_pass=True,
            reviewed_risk_tier="HIGH",
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["human_approval_supplied"])

    def test_task_range_escalation_requires_high_reviewed_tier(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(changed_path="backend/shopify/fixture.py")
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)

        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "LOW")
        self.assertEqual(evidence["risk_policy"]["effective_tier"], "HIGH")
        self.assertEqual(
            evidence["risk_policy"]["deterministic_escalation_paths"],
            ["backend/shopify/fixture.py"],
        )

        low = checkpoint_readiness(
            "S02-T01",
            repo.root,
            base_revision=base,
            snapshot_revision=snapshot,
            reviewed_digest=evidence["digest"],
            ai_review_pass=True,
            reviewed_risk_tier="LOW",
        )
        self.assertEqual(low["workflow_stage"], "BLOCKED")
        self.assertEqual(low["status"], "CHECKPOINT_NOT_READY")
        self.assertIn(
            "REVIEWED_RISK_TIER_BELOW_POLICY_MINIMUM",
            low["blocking_reasons"],
        )

        high = checkpoint_readiness(
            "S02-T01",
            repo.root,
            base_revision=base,
            snapshot_revision=snapshot,
            reviewed_digest=evidence["digest"],
            ai_review_pass=True,
            reviewed_risk_tier="HIGH",
        )
        self.assertEqual(high["workflow_stage"], "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(
            high["status"],
            "CHECKPOINT_READY — Awaiting explicit Human approval",
        )
        self.assertFalse(high["checkpoint_accepted"])

    def test_baseline_requires_fixed_integrated_or_exact_human_oid(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        initial = git(repo.root, "rev-parse", "HEAD")
        state = inspect(repo.root, implementation_authorized_task="S02-T01")
        self.assertEqual(state["ordered_candidate"], "S02-T01")
        self.assertEqual(state["executable_task"], "S02-T01")
        rejected = inspect(
            repo.root,
            implementation_authorized_task="S02-T01",
            approved_workflow_oid="deadbeef",
        )
        self.assertIsNone(rejected["executable_task"])
        accepted = inspect(
            repo.root,
            implementation_authorized_task="S02-T01",
            approved_workflow_oid=initial,
        )
        self.assertEqual(accepted["executable_task"], "S02-T01")

    def test_wrong_approved_oid_is_rejected(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        state = inspect(
            repo.root,
            implementation_authorized_task="S02-T01",
            approved_workflow_oid="deadbeef",
        )
        self.assertIsNone(state["executable_task"])

    def test_detached_self_report_old_schema_and_marker_do_not_unlock(self) -> None:
        holder, repo = self.repo(current_policy_at_head=False)
        self.addCleanup(holder.cleanup)
        state = inspect(repo.root, implementation_authorized_task="S02-T01")
        self.assertIsNone(state["executable_task"])
        policy_path = (
            repo.root
            / ".agents/skills/drone-slice-workflow/references/task-scope-policy.json"
        )
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["workflow_baseline_marker"] = "self-reported"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertIsNone(
            inspect(repo.root, implementation_authorized_task="S02-T01")[
                "executable_task"
            ]
        )

    def test_old_schema_policy_is_rejected(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        policy_path = (
            repo.root
            / ".agents/skills/drone-slice-workflow/references/task-scope-policy.json"
        )
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["schema_version"] = 1
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertIsNone(
            inspect(repo.root, implementation_authorized_task="S02-T01")[
                "executable_task"
            ]
        )

    def test_unconfigured_slice_and_task_fail_closed(self) -> None:
        holder, repo = self.repo(slice_name="slice-99-unknown")
        self.addCleanup(holder.cleanup)
        state = inspect(repo.root, implementation_authorized_task="S99-T01")
        self.assertIsNone(state["executable_task"])
        self.assertIn(
            "UNCONFIGURED_SLICE_POLICY",
            state["implementation_gate"]["blocking_reasons"],
        )

    def test_unconfigured_task_fails_closed(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        result = check("S02-T99", repo.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "ILLEGAL_OR_UNKNOWN_TASK_ID")

    def test_legacy_working_tree_review_is_compatibility_only(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        (repo.root / "backend/catalog/change.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        result = review_snapshot(repo.root)
        self.assertTrue(result["compatibility_only"])
        self.assertFalse(result["checkpoint_eligible"])
        self.assertFalse(result["integration_authorized"])

    def test_checkpoint_without_evidence_is_fail_closed(self) -> None:
        result = checkpoint_readiness("S02-T01", ".", verification_pass=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["workflow_stage"], "BLOCKED")
        self.assertEqual(result["status"], "CHECKPOINT_NOT_READY")
        self.assertFalse(result["human_approval_required"])

    def test_checkpoint_missing_reviewed_risk_tier_fails_closed(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)

        result = checkpoint_readiness(
            "S02-T01",
            repo.root,
            base_revision=base,
            snapshot_revision=snapshot,
            reviewed_digest=evidence["digest"],
            ai_review_pass=True,
        )

        self.assertEqual(result["workflow_stage"], "BLOCKED")
        self.assertEqual(result["status"], "CHECKPOINT_NOT_READY")
        self.assertIn("REVIEWED_RISK_TIER_REQUIRED", result["blocking_reasons"])

    def test_checkpoint_invalid_reviewed_risk_tier_fails_closed(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)

        result = checkpoint_readiness(
            "S02-T01",
            repo.root,
            base_revision=base,
            snapshot_revision=snapshot,
            reviewed_digest=evidence["digest"],
            ai_review_pass=True,
            reviewed_risk_tier="CRITICAL",
        )

        self.assertEqual(result["workflow_stage"], "BLOCKED")
        self.assertEqual(result["status"], "CHECKPOINT_NOT_READY")
        self.assertIn("REVIEWED_RISK_TIER_INVALID", result["blocking_reasons"])

    def test_checkpoint_cli_stage_matches_evidence_readiness(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        common = [
            sys.executable,
            str(VERIFY_COMMIT_SCRIPT),
            "S02-T01",
            "--checkpoint",
            "--repo",
            str(repo.root),
            "--base-head",
            base,
            "--snapshot-head",
            snapshot,
            "--ai-review-pass",
            "--risk-tier",
            "LOW",
        ]

        missing_risk = subprocess.run(
            [*common[:-2], "--reviewed-digest", evidence["digest"]],
            check=False,
            capture_output=True,
            text=True,
        )
        missing_risk_payload = json.loads(missing_risk.stdout)
        self.assertEqual(missing_risk.returncode, 1)
        self.assertEqual(missing_risk_payload["workflow_stage"], "BLOCKED")
        self.assertEqual(missing_risk_payload["status"], "CHECKPOINT_NOT_READY")
        self.assertIn(
            "REVIEWED_RISK_TIER_REQUIRED",
            missing_risk_payload["blocking_reasons"],
        )

        invalid = subprocess.run(
            [*common, "--reviewed-digest", "0" * 64],
            check=False,
            capture_output=True,
            text=True,
        )
        invalid_payload = json.loads(invalid.stdout)
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(invalid_payload["workflow_stage"], "BLOCKED")
        self.assertEqual(invalid_payload["status"], "CHECKPOINT_NOT_READY")

        ready = subprocess.run(
            [*common, "--reviewed-digest", evidence["digest"]],
            check=False,
            capture_output=True,
            text=True,
        )
        ready_payload = json.loads(ready.stdout)
        self.assertEqual(ready.returncode, 1)
        self.assertEqual(ready_payload["workflow_stage"], "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(
            ready_payload["status"],
            "CHECKPOINT_READY — Awaiting explicit Human approval",
        )
        self.assertFalse(ready_payload["checkpoint_accepted"])

    def test_policy_has_explicit_completion_task_and_no_auto_checkpoint_semantics(
        self,
    ) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        serialized = json.dumps(policy, sort_keys=True)
        self.assertNotIn("policy-controlled", serialized)
        for slice_policy in policy["slices"].values():
            self.assertIn(slice_policy["completion_task"], slice_policy["tasks"])
            for task_policy in slice_policy["tasks"].values():
                self.assertEqual(task_policy["checkpoint_policy"], "human-decision")


if __name__ == "__main__":
    unittest.main()
