#!/usr/bin/env python3
"""Standard-library regression tests for workflow helper safety properties."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from check_scope import check
from verify_commit_readiness import review_snapshot, verify, working_diff_sha256
from verify_task import verify as verify_task

TASK_TITLES = {
    "T01": "Bootstrap",
    "T02": "Contracts",
    "T03": "Read fixture",
    "T04": "Walking skeleton",
    "T05": "Identity",
    "T06": "Fallback",
    "T07": "Scope guards",
    "T08": "Thin API",
    "T09": "Closure",
}
DEPENDENCIES = {
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


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def task_statuses(
    active: str | None = None, done_through: str = "T05"
) -> dict[str, str]:
    done_number = int(done_through[1:])
    statuses = {
        task_id: "DONE" if int(task_id[1:]) <= done_number else "NOT_STARTED"
        for task_id in TASK_TITLES
    }
    if active:
        statuses[active] = "IN_PROGRESS"
    return statuses


def task_table(statuses: dict[str, str]) -> str:
    rows = [
        "| Task | Title | Status | Dependencies |",
        "|---|---|---|---|",
    ]
    rows.extend(
        f"| {task_id} | {TASK_TITLES[task_id]} | {statuses[task_id]} | "
        f"{DEPENDENCIES[task_id]} |"
        for task_id in TASK_TITLES
    )
    return "\n".join(rows) + "\n"


class TemporaryRepository:
    def __init__(
        self,
        root: Path,
        *,
        active: str | None = None,
        done_through: str = "T05",
        slice_name: str = "slice-01-product-facts",
    ) -> None:
        self.root = root
        git(root, "init", "-q")
        git(root, "config", "user.name", "Workflow Test")
        git(root, "config", "user.email", "workflow-test@example.invalid")
        tasks = root / "changes" / slice_name / "tasks.md"
        tasks.parent.mkdir(parents=True)
        tasks.write_text(
            task_table(task_statuses(active, done_through)), encoding="utf-8"
        )
        (root / "backend" / "application").mkdir(parents=True)
        (root / "backend" / "application" / "value.py").write_text(
            'VALUE = "base"\n', encoding="utf-8"
        )
        (root / "pyproject.toml").write_text(
            "[project]\nname='test'\n", encoding="utf-8"
        )
        (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "initial")


class WorkflowScriptTests(unittest.TestCase):
    def test_digest_is_staging_invariant_but_head_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            TemporaryRepository(repo, active="T06")
            changed = repo / "backend" / "application" / "value.py"
            changed.write_text('VALUE = "reviewed"\n', encoding="utf-8")
            first_head = git(repo, "rev-parse", "HEAD")
            unstaged_hash = working_diff_sha256(repo, "T06")

            git(repo, "add", "backend/application/value.py")
            self.assertEqual(unstaged_hash, working_diff_sha256(repo, "t06"))
            git(repo, "restore", "--staged", "backend/application/value.py")

            marker = repo / "baseline-marker.txt"
            marker.write_text("new baseline\n", encoding="utf-8")
            git(repo, "add", "baseline-marker.txt")
            git(repo, "commit", "-qm", "move baseline")
            self.assertNotEqual(first_head, git(repo, "rev-parse", "HEAD"))
            self.assertNotEqual(unstaged_hash, working_diff_sha256(repo, "T06"))

    def test_commit_readiness_rejects_changed_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            TemporaryRepository(repo, done_through="T06")
            changed = repo / "backend" / "application" / "value.py"
            changed.write_text('VALUE = "reviewed"\n', encoding="utf-8")
            reviewed_head = git(repo, "rev-parse", "HEAD")
            reviewed_hash = working_diff_sha256(repo, "T06")
            git(repo, "add", "backend/application/value.py")

            marker = repo / "baseline-marker.txt"
            marker.write_text("new baseline\n", encoding="utf-8")
            git(repo, "add", "baseline-marker.txt")
            git(repo, "commit", "-qm", "move baseline", "--only", "baseline-marker.txt")

            result = verify(
                "T06",
                reviewed_head,
                reviewed_hash,
                repo,
                ai_review_pass=True,
                human_approved=True,
            )
            self.assertFalse(result["ok"])
            self.assertIn("REVIEWED_HEAD_MISMATCH", result["blocking_reasons"])
            self.assertIn("REVIEWED_DIFF_HASH_MISMATCH", result["blocking_reasons"])

    def test_commit_readiness_accepts_same_head_after_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            TemporaryRepository(repo, done_through="T06")
            changed = repo / "backend" / "application" / "value.py"
            changed.write_text('VALUE = "reviewed"\n', encoding="utf-8")
            reviewed_head = git(repo, "rev-parse", "HEAD")
            reviewed_hash = working_diff_sha256(repo, "T06")
            git(repo, "add", "backend/application/value.py")

            result = verify(
                "T06",
                reviewed_head,
                reviewed_hash,
                repo,
                ai_review_pass=True,
                human_approved=True,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["workflow_stage"], "COMMIT_READY")

    def test_snapshot_is_task_bound_and_rejects_other_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            TemporaryRepository(repo, active="T07", done_through="T06")
            changed = repo / "backend" / "application" / "value.py"
            changed.write_text('VALUE = "t07-reviewed"\n', encoding="utf-8")

            t07_snapshot = review_snapshot("t07", repo)
            self.assertTrue(t07_snapshot["ok"])
            self.assertEqual(t07_snapshot["task"], "T07")
            self.assertEqual(t07_snapshot["actual_active_tasks"], ["T07"])
            t06_snapshot = review_snapshot("T06", repo)
            self.assertFalse(t06_snapshot["ok"])
            self.assertIn(
                "DIFFERENT_ACTIVE_TASK_IN_PROGRESS",
                t06_snapshot["blocking_reasons"],
            )
            self.assertNotEqual(
                t07_snapshot["current_diff_sha256"],
                working_diff_sha256(repo, "T06"),
            )

            git(repo, "add", "backend/application/value.py")
            result = verify(
                "T06",
                t07_snapshot["base_head"],
                t07_snapshot["current_diff_sha256"],
                repo,
                ai_review_pass=True,
                human_approved=True,
            )
            self.assertFalse(result["ok"])
            self.assertIn(
                "DIFFERENT_ACTIVE_TASK_IN_PROGRESS", result["blocking_reasons"]
            )
            self.assertIn("REVIEWED_DIFF_HASH_MISMATCH", result["blocking_reasons"])

    def test_dependency_confirmation_is_required_only_for_dependency_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            TemporaryRepository(repo, done_through="T08")
            (repo / "pyproject.toml").write_text(
                "[project]\nname='test'\ndependencies=['large-framework']\n",
                encoding="utf-8",
            )
            reviewed_head = git(repo, "rev-parse", "HEAD")
            reviewed_hash = working_diff_sha256(repo, "T08")
            git(repo, "add", "pyproject.toml")

            missing_confirmation = verify(
                "T08",
                reviewed_head,
                reviewed_hash,
                repo,
                ai_review_pass=True,
                human_approved=True,
            )
            self.assertFalse(missing_confirmation["ok"])
            self.assertIn(
                "DEPENDENCY_MANUAL_CONFIRMATION_REQUIRED",
                missing_confirmation["blocking_reasons"],
            )
            self.assertTrue(
                missing_confirmation["dependency_review_evidence"]["required"]
            )
            self.assertFalse(
                missing_confirmation["dependency_review_evidence"][
                    "confirmed_from_current_workflow_context"
                ]
            )

            confirmed = verify(
                "T08",
                reviewed_head,
                reviewed_hash,
                repo,
                ai_review_pass=True,
                human_approved=True,
                dependency_review_confirmed=True,
            )
            self.assertTrue(confirmed["ok"])
            self.assertEqual(confirmed["workflow_stage"], "COMMIT_READY")

    def test_unconfigured_slice_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            TemporaryRepository(
                repo,
                active="T01",
                done_through="T01",
                slice_name="slice-02-unconfigured",
            )
            result = check("T01", repo)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "UNCONFIGURED_SLICE_POLICY")

    def test_dependency_policy_is_task_aware(self) -> None:
        for task_id, done_through in (("T01", "T01"), ("T02", "T01"), ("T08", "T07")):
            with self.subTest(task=task_id), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory)
                TemporaryRepository(repo, active=task_id, done_through=done_through)
                (repo / "pyproject.toml").write_text(
                    "[project]\nname='test'\ndependencies=['minimal']\n",
                    encoding="utf-8",
                )
                result = check(task_id, repo)
                self.assertTrue(result["ok"])
                self.assertTrue(
                    result["dependency_review"]["manual_confirmation_required"]
                )
                plan = verify_task(task_id, repo, plan_only=True)
                self.assertTrue(plan["ok"])
                self.assertEqual(
                    plan["dependency_gate_mode"], "plan-authorized-minimal"
                )
                self.assertFalse(
                    any(
                        command.endswith("-- pyproject.toml uv.lock")
                        for command in plan["planned_commands"]
                    )
                )

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            TemporaryRepository(repo, active="T06")
            (repo / "pyproject.toml").write_text(
                "[project]\nname='test'\ndependencies=['not-authorized']\n",
                encoding="utf-8",
            )
            result = check("T06", repo)
            self.assertFalse(result["ok"])
            self.assertIn(
                "DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY",
                result["blocking_reasons"],
            )
            plan = verify_task("T06", repo, plan_only=True)
            self.assertFalse(plan["ok"])
            self.assertTrue(
                any(
                    command.endswith("-- pyproject.toml uv.lock")
                    for command in plan["planned_commands"]
                )
            )


if __name__ == "__main__":
    unittest.main()
