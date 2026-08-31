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
from unittest.mock import patch

from check_scope import POLICY_PATH, check, check_slice_range
from inspect_state import inspect
from verify_commit_readiness import (
    checkpoint_readiness,
    commit_range_sha256,
    immutable_evidence,
    review_snapshot,
)
from verify_task import verify as verify_task_runner

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
            "import pytest\n\n\n@pytest.mark.unit\ndef test_fixture():\n"
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

    def test_slice_review_verification_uses_union_scope(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        for relative in (
            "backend/catalog/change.py",
            "backend/conversation/change.py",
            "backend/evidence/change.py",
        ):
            path = repo.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = 1\n", encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S02): multi-task slice snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        slice_scope = check_slice_range(
            "S02-T07", repo.root, base_head=base, snapshot_head=snapshot
        )
        task_scope = check("S02-T07", repo.root, base_head=base, snapshot_head=snapshot)
        self.assertTrue(slice_scope["ok"], slice_scope)
        self.assertEqual(slice_scope["scope_kind"], "slice-range")
        self.assertFalse(task_scope["ok"])
        self.assertIn("PATH_OUTSIDE_TASK_SCOPE", task_scope["blocking_reasons"])

        verification = verify_task_runner(
            "S02-T07",
            repo.root,
            full=True,
            base_head=base,
            snapshot_head=snapshot,
            slice_review=True,
        )
        self.assertTrue(verification["ok"], verification)
        self.assertTrue(verification["slice_review"])
        self.assertTrue(verification["verification_complete"])

    def test_slice_review_verification_uses_union_dependency_policy(self) -> None:
        holder, repo = self.repo(slice_name="slice-01-product-facts")
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T09"))
        pyproject = repo.root / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8") + "\n# slice review fixture\n",
            encoding="utf-8",
        )
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S01): dependency-bearing slice")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        slice_scope = check_slice_range(
            "S01-T09", repo.root, base_head=base, snapshot_head=snapshot
        )
        task_scope = check("S01-T09", repo.root, base_head=base, snapshot_head=snapshot)
        self.assertTrue(slice_scope["ok"], slice_scope)
        self.assertEqual(
            slice_scope["dependency_review"]["changed_paths"], ["pyproject.toml"]
        )
        self.assertTrue(slice_scope["dependency_review"]["allowed_by_task_policy"])
        self.assertFalse(task_scope["ok"])
        self.assertIn(
            "DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY",
            task_scope["blocking_reasons"],
        )

        verification = verify_task_runner(
            "S01-T09",
            repo.root,
            full=True,
            base_head=base,
            snapshot_head=snapshot,
            slice_review=True,
        )
        self.assertTrue(verification["ok"], verification)
        self.assertTrue(verification["slice_review"])
        planned = "\n".join(verification["planned_commands"])
        self.assertNotIn("-- .python-version pyproject.toml uv.lock", planned)

    def test_slice_review_checkpoint_requests_slice_aware_verification(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        for relative in (
            "backend/catalog/change.py",
            "backend/conversation/change.py",
            "backend/evidence/change.py",
        ):
            path = repo.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = 1\n", encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S02): checkpoint snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence(
            "S02-T07", base, snapshot, repo.root, mode="slice-review"
        )
        verification = {
            "ok": True,
            "verification_complete": True,
            "task": "S02-T07",
            "base_head": base,
            "snapshot_head": snapshot,
            "results": [{"command": "full", "exit_code": 0}],
        }
        with patch(
            "verify_commit_readiness.verify_task", return_value=verification
        ) as run:
            result = checkpoint_readiness(
                "S02-T07",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                mode="slice-review",
                ai_review_pass=True,
                reviewed_risk_tier="HIGH",
            )
        self.assertFalse(result["ok"])
        self.assertTrue(result["human_approval_required"])
        self.assertEqual(run.call_args.kwargs["full"], True)
        self.assertEqual(run.call_args.kwargs["slice_review"], True)

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
        self.assertTrue(result["ok"])
        self.assertEqual(result["workflow_stage"], "AUTO_ADVANCE_ELIGIBLE")
        self.assertEqual(result["reason"], "LOW_RISK_AI_REVIEW_ADVANCE_ALLOWED")
        self.assertTrue(result["auto_advance"])
        self.assertFalse(result["human_approval_required"])
        self.assertFalse(result["checkpoint_accepted"])
        self.assertFalse(result["integration_authorized"])
        self.assertFalse(result["push_authorized"])

    def test_low_review_auto_advances_but_medium_and_high_need_human(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        low = checkpoint_readiness(
            "S02-T01",
            repo.root,
            base_revision=base,
            snapshot_revision=snapshot,
            reviewed_digest=evidence["digest"],
            ai_review_pass=True,
            reviewed_risk_tier="LOW",
        )
        self.assertTrue(low["ok"])
        self.assertEqual(low["workflow_stage"], "AUTO_ADVANCE_ELIGIBLE")
        self.assertFalse(low["human_approval_required"])

        medium_base, medium_snapshot = repo.snapshot(
            task_id="T02", changed_path="backend/conversation/change.py"
        )
        git(repo.root, "switch", "--detach", medium_snapshot)
        medium_evidence = immutable_evidence(
            "S02-T02", medium_base, medium_snapshot, repo.root
        )
        medium = checkpoint_readiness(
            "S02-T02",
            repo.root,
            base_revision=medium_base,
            snapshot_revision=medium_snapshot,
            reviewed_digest=medium_evidence["digest"],
            ai_review_pass=True,
            reviewed_risk_tier="MEDIUM",
        )
        self.assertFalse(medium["ok"])
        self.assertTrue(medium["human_approval_required"])

        high_base, high_snapshot = repo.snapshot(
            task_id="T05", changed_path="backend/evidence/change.py"
        )
        git(repo.root, "switch", "--detach", high_snapshot)
        high_evidence = immutable_evidence(
            "S02-T05", high_base, high_snapshot, repo.root
        )
        high = checkpoint_readiness(
            "S02-T05",
            repo.root,
            base_revision=high_base,
            snapshot_revision=high_snapshot,
            reviewed_digest=high_evidence["digest"],
            ai_review_pass=True,
            reviewed_risk_tier="HIGH",
        )
        self.assertFalse(high["ok"])
        self.assertTrue(high["human_approval_required"])

    def test_reviewer_higher_tier_escalates_low_policy(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        verification = {
            "ok": True,
            "verification_complete": True,
            "task": "S02-T01",
            "base_head": base,
            "snapshot_head": snapshot,
            "results": [{"command": "targeted", "exit_code": 0}],
        }
        with patch(
            "verify_commit_readiness.verify_task", return_value=verification
        ) as run:
            result = checkpoint_readiness(
                "S02-T01",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                ai_review_pass=True,
                reviewed_risk_tier="HIGH",
            )
        self.assertEqual(result["reviewed_effective_tier"], "HIGH")
        self.assertEqual(result["workflow_stage"], "HUMAN_APPROVAL_REQUIRED")
        self.assertFalse(result["auto_advance"])
        run.assert_called_once()

    def test_checkpoint_requires_successful_targeted_verification(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        failed_verification = {
            "ok": False,
            "verification_complete": True,
            "results": [{"command": "targeted", "exit_code": 1}],
        }
        with patch(
            "verify_commit_readiness.verify_task", return_value=failed_verification
        ):
            result = checkpoint_readiness(
                "S02-T01",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                ai_review_pass=True,
                reviewed_risk_tier="LOW",
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["workflow_stage"], "BLOCKED")
        self.assertIn("TARGETED_VERIFICATION_FAILED", result["blocking_reasons"])

    def test_plan_only_is_not_verification_evidence(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        result = verify_task_runner("S02-T01", repo.root, plan_only=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["verification_complete"])
        self.assertEqual(result["results"], [])

    def test_slice_review_requires_immutable_range_for_verification(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        result = verify_task_runner(
            "S02-T07", repo.root, plan_only=True, slice_review=True
        )
        self.assertFalse(result["ok"])
        self.assertFalse(result["verification_complete"])
        self.assertEqual(result["error"], "SLICE_REVIEW_IMMUTABLE_RANGE_REQUIRED")

    def test_slice_authorization_only_unlocks_low_ordered_task(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)

        state = inspect(repo.root, implementation_authorized_slice="S02")
        self.assertEqual(state["ordered_candidate"], "S02-T01")
        self.assertEqual(state["executable_task"], "S02-T01")
        self.assertEqual(
            state["tasks"][0]["implementation_authorized_via"], "slice-low"
        )

        base, snapshot = repo.snapshot(task_id="T01")
        git(repo.root, "switch", "--detach", snapshot)
        state = inspect(repo.root, implementation_authorized_slice="S02")
        self.assertEqual(state["ordered_candidate"], "S02-T02")
        self.assertIsNone(state["executable_task"])
        candidate = next(item for item in state["tasks"] if item["id"] == "T02")
        self.assertIn(
            "SLICE_AUTHORIZATION_REQUIRES_LOW_RISK_TASK",
            candidate["execution_blockers"],
        )

    def test_slice_authorization_rejects_wrong_slice(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        with self.assertRaises(Exception):
            inspect(repo.root, implementation_authorized_slice="S01")

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
        self.assertEqual(ready.returncode, 0)
        self.assertEqual(ready_payload["workflow_stage"], "AUTO_ADVANCE_ELIGIBLE")
        self.assertEqual(ready_payload["status"], "AUTO_ADVANCE_ELIGIBLE")
        self.assertTrue(ready_payload["auto_advance"])
        self.assertFalse(ready_payload["checkpoint_accepted"])

    def test_policy_has_explicit_completion_task_and_no_auto_checkpoint_semantics(
        self,
    ) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        serialized = json.dumps(policy, sort_keys=True)
        self.assertNotIn("policy-controlled", serialized)
        for slice_policy in policy["slices"].values():
            self.assertIn(slice_policy["completion_task"], slice_policy["tasks"])
            execution_policy = slice_policy["execution_policy"]
            self.assertEqual(execution_policy["implementation_session"], "slice")
            self.assertTrue(execution_policy["targeted_verification_per_task"])
            self.assertEqual(execution_policy["full_suite"], "slice-completion")
            self.assertEqual(
                execution_policy["human_gates"],
                {
                    "LOW": "slice-completion",
                    "MEDIUM": "key-checkpoint",
                    "HIGH": "task",
                },
            )
            for task_policy in slice_policy["tasks"].values():
                self.assertEqual(task_policy["checkpoint_policy"], "human-decision")
                automation = task_policy.get("automation")
                if automation:
                    self.assertTrue(automation["review_required"])
                    self.assertIn(
                        automation["human_gate"],
                        {"slice-completion", "key-checkpoint", "task"},
                    )
                    if task_policy["risk_tier"] == "LOW":
                        self.assertTrue(automation["auto_advance"])
                        self.assertEqual(automation["human_gate"], "slice-completion")
                    else:
                        self.assertFalse(automation["auto_advance"])


if __name__ == "__main__":
    unittest.main()
