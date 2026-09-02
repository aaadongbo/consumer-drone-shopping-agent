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
from verify_task import command_plan
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
SLICE_3_TITLES = {
    "T01": "Target Resolution contract",
    "T02": "Confirmed context reducer",
    "T03": "Explicit reference resolution",
    "T04": "Turn Target precedence",
    "T05": "Product Fact walking skeleton",
    "T06": "Typed routing handoff",
    "T07": "Completion evidence",
}
SLICE_3_DEPENDENCIES = {
    "T01": "Human-approved Planning Baseline + S03 workflow policy",
    "T02": "T01",
    "T03": "T01",
    "T04": "T02, T03",
    "T05": "T04",
    "T06": "T05",
    "T07": "T06",
}
SLICE_4_TITLES = {
    "T01": "Comparison set identity and provenance contract",
    "T02": "Bounded member validation and resolution",
    "T03": "Per-member normalized facts and Evidence binding",
    "T04": "Read-only dynamic facts and freshness guard",
    "T05": "Comparison answer / fallback walking skeleton",
    "T06": "Slice 4 verification matrix and completion evidence",
}
SLICE_4_DEPENDENCIES = {
    "T01": (
        "Slice 3 completion + Slice 4 planning approval + stable Shopify Variant "
        "ID mapping"
    ),
    "T02": "T01",
    "T03": "T02",
    "T04": "T02, T03",
    "T05": "T03, T04",
    "T06": "T05",
}
SLICE_5_TITLES = {
    "T01": "Document manifest and ingestion contract",
    "T02": "Scoped chunking and locator baseline",
    "T03": "Metadata-filtered baseline retrieval",
    "T04": "Evidence quality and claim coverage gate",
    "T05": "Bounded Product RAG action loop",
    "T06": "Product RAG answer/fallback walking skeleton",
    "T07": "Slice 5 evaluation matrix and completion evidence",
}
SLICE_5_DEPENDENCIES = {
    "T01": "Slice 4 completion + Slice 5 planning approval + S05 workflow policy",
    "T02": "T01",
    "T03": "T02",
    "T04": "T03",
    "T05": "T04",
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


def successful_verification(
    task: str, base: str, snapshot: str, *, slice_review: bool = False
) -> dict[str, object]:
    return {
        "ok": True,
        "task": task,
        "base_head": base,
        "snapshot_head": snapshot,
        "verification_complete": True,
        "slice_review": slice_review,
        "results": [{"command": "targeted gates", "exit_code": 0}],
    }


def reviewer_evidence(
    immutable: dict[str, object], *, findings: list[object] | None = None
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "verdict": "AI_REVIEW_PASS",
        "slice": immutable["slice"],
        "task": immutable["task"],
        "base_head": immutable["base_head"],
        "snapshot_head": immutable["snapshot_head"],
        "mode": immutable["mode"],
        "digest": immutable["digest"],
        "risk_tier": (immutable["risk_policy"] or {})["effective_tier"],
        "reviewer": {
            "identity": "reviewer-agent",
            "session": "fresh-child-session",
            "kind": "independent-child",
        },
        "review_worktree": {
            "path": "/tmp/independent-review",
            "head": immutable["snapshot_head"],
            "detached": True,
            "clean": True,
        },
        "no_write": True,
        "findings": [] if findings is None else findings,
        "verification": {
            "commands": [
                {"command": "python -m pytest", "exit_code": 0, "result": "passed"}
            ]
        },
    }


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
            self.titles, self.dependencies = (
                dict(SLICE_1_TITLES),
                dict(SLICE_1_DEPENDENCIES),
            )
        elif slice_name == "slice-03-target-resolution":
            self.titles, self.dependencies = (
                dict(SLICE_3_TITLES),
                dict(SLICE_3_DEPENDENCIES),
            )
        elif slice_name == "slice-04-variant-comparison":
            self.titles, self.dependencies = (
                dict(SLICE_4_TITLES),
                dict(SLICE_4_DEPENDENCIES),
            )
        elif slice_name == "slice-05-product-rag":
            self.titles, self.dependencies = (
                dict(SLICE_5_TITLES),
                dict(SLICE_5_DEPENDENCIES),
            )
        else:
            self.titles, self.dependencies = (
                dict(SLICE_2_TITLES),
                dict(SLICE_2_DEPENDENCIES),
            )
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
            "backend/agent",
            "backend/api",
            "backend/catalog",
            "backend/conversation",
            "backend/evidence",
            "backend/common",
            "backend/application",
            "backend/rag",
            "eval/datasets",
            "tests/contract",
            "tests/e2e",
            "tests/integration",
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

    def workflow_policy_snapshot(
        self,
        *,
        extra_path: str | None = None,
    ) -> tuple[str, str]:
        base = git(self.root, "rev-parse", "HEAD")
        changes = {
            ".agents/skills/drone-slice-workflow/SKILL.md": ("# workflow policy\n"),
            ".agents/skills/drone-slice-workflow/references/review-checklist.md": (
                "# workflow review\n"
            ),
            ".agents/skills/drone-slice-workflow/references/execution-protocol.md": (
                "# workflow execution\n"
            ),
            ".agents/skills/drone-slice-workflow/references/task-scope-policy.json": (
                (
                    self.root / ".agents/skills/drone-slice-workflow/references/"
                    "task-scope-policy.json"
                ).read_text(encoding="utf-8")
                + "\n"
            ),
            ".agents/skills/drone-slice-workflow/scripts/inspect_state.py": (
                "WORKFLOW_GATED_TASK_FILES = set()\n"
            ),
            ".agents/skills/drone-slice-workflow/scripts/"
            "test_workflow_scripts.py": "def test_policy():\n    pass\n",
            ".agents/skills/drone-slice-workflow/scripts/check_scope.py": (
                "def check():\n    pass\n"
            ),
            ".agents/skills/drone-slice-workflow/scripts/"
            "verify_commit_readiness.py": "def evidence():\n    pass\n",
            ".agents/skills/drone-slice-workflow/scripts/verify_task.py": (
                "def verify():\n    pass\n"
            ),
        }
        if extra_path:
            changes[extra_path] = "extra\n"
        for relative, content in changes.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "wip(WORKFLOW-S03-POLICY): snapshot")
        return base, git(self.root, "rev-parse", "HEAD")


class WorkflowScriptTests(unittest.TestCase):
    def repo(
        self, **kwargs: object
    ) -> tuple[tempfile.TemporaryDirectory[str], TemporaryRepository]:
        holder = tempfile.TemporaryDirectory()
        return holder, TemporaryRepository(Path(holder.name), **kwargs)

    def test_task_validation_is_changed_path_targeted_and_boundary_full(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        slice_policy = policy["slices"][
            "changes/slice-02-single-turn-recommendation/tasks.md"
        ]
        task_policy = slice_policy["tasks"]["T02"]
        targeted, _ = command_plan(
            task_policy,
            slice_policy,
            {"dependency_review": {"changed_paths": []}},
            False,
            None,
            None,
            ["backend/conversation/reducer.py", "tests/unit/test_reducer.py"],
        )
        self.assertIn(
            [
                "uv",
                "run",
                "ruff",
                "check",
                "backend/conversation/reducer.py",
                "tests/unit/test_reducer.py",
            ],
            targeted,
        )
        self.assertNotIn(["uv", "lock", "--check"], targeted)
        self.assertNotIn(["uv", "run", "ruff", "check", "."], targeted)
        self.assertIn(
            [
                "uv",
                "run",
                "pytest",
                "-m",
                "unit or contract",
                "tests/unit/test_reducer.py",
                "-q",
            ],
            targeted,
        )

        boundary, _ = command_plan(
            task_policy,
            slice_policy,
            {"dependency_review": {"changed_paths": ["uv.lock"]}},
            False,
            None,
            None,
            ["backend/conversation/reducer.py", "uv.lock"],
        )
        self.assertIn(["uv", "lock", "--check"], boundary)
        self.assertIn(["uv", "run", "ruff", "check", "."], boundary)

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

    def test_future_draft_tasks_without_formal_status_are_ignored(self) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        future_tasks = repo.root / "changes/slice-05-product-rag/tasks.md"
        future_tasks.parent.mkdir(parents=True, exist_ok=True)
        future_tasks.write_text(
            "| Planned Task | Title | Planned state | Dependencies |\n"
            "|---|---|---|---|\n"
            "| T01 | Future task | PLANNED | later |\n",
            encoding="utf-8",
        )

        state = inspect(repo.root)

        self.assertEqual(
            state["tasks_file"], "changes/slice-03-target-resolution/tasks.md"
        )
        self.assertEqual(state["ordered_candidate"], "S03-T01")

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
            plan_only=True,
            base_head=base,
            snapshot_head=snapshot,
            slice_review=True,
        )
        self.assertFalse(verification["ok"])
        self.assertTrue(verification["slice_review"])
        self.assertFalse(verification["verification_complete"])
        self.assertTrue(verification["scope"]["ok"], verification)

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
            plan_only=True,
            base_head=base,
            snapshot_head=snapshot,
            slice_review=True,
        )
        self.assertFalse(verification["ok"])
        self.assertTrue(verification["slice_review"])
        self.assertFalse(verification["verification_complete"])
        self.assertTrue(verification["scope"]["ok"], verification)
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

    def test_slice_review_rejects_tasks_table_only_completion(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S02): status-only completion")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S02-T07", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertFalse(evidence["ok"])
        self.assertIn(
            "SLICE_COMPLETION_WITHOUT_IMPLEMENTATION_SCOPE",
            evidence["blocking_reasons"],
        )

    def test_malformed_task_status_row_fails_closed(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        repo.tasks_path.write_text(
            repo.tasks_path.read_text(encoding="utf-8")
            + "| T10 | Malformed row | DONE | T09\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(Exception, "malformed Task status row"):
            inspect(repo.root)

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
        verification = successful_verification("S02-T01", base, snapshot)
        with patch("verify_commit_readiness.verify_task", return_value=verification):
            result = checkpoint_readiness(
                "S02-T01",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                verification_pass=True,
                reviewed_risk_tier="LOW",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["workflow_stage"], "AUTO_ADVANCE_ELIGIBLE")
        self.assertEqual(result["reason"], "PLANNED_TASK_AI_REVIEW_ADVANCE_ALLOWED")
        self.assertTrue(result["auto_advance"])
        self.assertFalse(result["human_approval_required"])
        self.assertFalse(result["checkpoint_accepted"])
        self.assertFalse(result["integration_authorized"])
        self.assertFalse(result["push_authorized"])

    def test_medium_auto_advances_but_high_requires_human_decision(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot()
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T01", base, snapshot, repo.root)
        low_verification = successful_verification("S02-T01", base, snapshot)
        with patch(
            "verify_commit_readiness.verify_task", return_value=low_verification
        ):
            low = checkpoint_readiness(
                "S02-T01",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
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
        medium_verification = successful_verification(
            "S02-T02", medium_base, medium_snapshot
        )
        with patch(
            "verify_commit_readiness.verify_task", return_value=medium_verification
        ):
            medium = checkpoint_readiness(
                "S02-T02",
                repo.root,
                base_revision=medium_base,
                snapshot_revision=medium_snapshot,
                reviewed_digest=medium_evidence["digest"],
                reviewer_evidence=reviewer_evidence(medium_evidence),
                reviewed_risk_tier="MEDIUM",
            )
        self.assertTrue(medium["ok"])
        self.assertFalse(medium["human_approval_required"])

        high_base, high_snapshot = repo.snapshot(
            task_id="T05", changed_path="backend/evidence/change.py"
        )
        git(repo.root, "switch", "--detach", high_snapshot)
        high_evidence = immutable_evidence(
            "S02-T05", high_base, high_snapshot, repo.root
        )
        high_verification = successful_verification("S02-T05", high_base, high_snapshot)
        with patch(
            "verify_commit_readiness.verify_task", return_value=high_verification
        ):
            high = checkpoint_readiness(
                "S02-T05",
                repo.root,
                base_revision=high_base,
                snapshot_revision=high_snapshot,
                reviewed_digest=high_evidence["digest"],
                reviewed_risk_tier="HIGH",
            )
        self.assertFalse(high["ok"])
        self.assertTrue(high["human_approval_required"])
        self.assertIn("HIGH_RISK_HUMAN_DECISION_REQUIRED", high["blocking_reasons"])

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

    def test_slice_authorization_unlocks_selected_planned_task(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)

        state = inspect(repo.root, implementation_authorized_slice="S02")
        self.assertEqual(state["ordered_candidate"], "S02-T01")
        self.assertEqual(state["executable_task"], "S02-T01")
        self.assertEqual(state["tasks"][0]["implementation_authorized_via"], "slice")

        base, snapshot = repo.snapshot(task_id="T01")
        git(repo.root, "switch", "--detach", snapshot)
        state = inspect(repo.root, implementation_authorized_slice="S02")
        self.assertEqual(state["ordered_candidate"], "S02-T02")
        self.assertEqual(state["executable_task"], "S02-T02")

    def test_slice_authorization_rejects_wrong_slice(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        with self.assertRaises(Exception):
            inspect(repo.root, implementation_authorized_slice="S01")

    def test_s03_tasks_are_configured_and_t01_requires_task_authorization(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)

        state = inspect(repo.root)

        self.assertEqual(
            [task["canonical_id"] for task in state["tasks"]],
            [
                "S03-T01",
                "S03-T02",
                "S03-T03",
                "S03-T04",
                "S03-T05",
                "S03-T06",
                "S03-T07",
            ],
        )
        self.assertEqual(state["ordered_candidate"], "S03-T01")
        self.assertIsNone(state["executable_task"])
        t01 = next(item for item in state["tasks"] if item["id"] == "T01")
        self.assertIn(
            "CURRENT_CONTEXT_IMPLEMENTATION_AUTHORIZATION_REQUIRED",
            t01["execution_blockers"],
        )
        self.assertEqual(t01["automation_policy"]["human_gate"], "unplanned-exception")
        self.assertTrue(t01["automation_policy"]["auto_advance"])
        self.assertEqual(t01["automation_policy"]["review_cadence"], "human-decision")

        slice_authorized = inspect(repo.root, implementation_authorized_slice="S03")
        self.assertIsNone(slice_authorized["executable_task"])
        self.assertIn(
            "HIGH_RISK_HUMAN_DECISION_REQUIRED",
            slice_authorized["tasks"][0]["execution_blockers"],
        )

        task_authorized = inspect(repo.root, implementation_authorized_task="S03-T01")
        self.assertEqual(task_authorized["executable_task"], "S03-T01")

    def test_s03_t01_public_contract_change_requires_human_escalation(self) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(
            task_id="T01", changed_path="backend/common/contracts.py"
        )
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("S03-T01", base, snapshot, repo.root)
        verification = {
            "ok": True,
            "verification_complete": True,
            "task": "S03-T01",
            "base_head": base,
            "snapshot_head": snapshot,
            "results": [{"command": "targeted", "exit_code": 0}],
        }
        with patch(
            "verify_commit_readiness.verify_task", return_value=verification
        ) as run:
            result = checkpoint_readiness(
                "S03-T01",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                reviewed_risk_tier="HIGH",
            )

        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "HIGH")
        self.assertTrue(evidence["risk_policy"]["automation"]["auto_advance"])
        self.assertIn(
            "backend/common/contracts.py",
            evidence["risk_policy"]["deterministic_escalation_paths"],
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["workflow_stage"], "HUMAN_APPROVAL_REQUIRED")
        self.assertTrue(result["human_approval_required"])
        self.assertTrue(run.call_args.kwargs["full"])

    def test_s03_scope_accepts_task_paths_and_rejects_forbidden_paths(self) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(
            task_id="T03", changed_path="backend/catalog/alias_registry.py"
        )
        git(repo.root, "switch", "--detach", snapshot)
        allowed = check("S03-T03", repo.root, base_head=base, snapshot_head=snapshot)
        self.assertTrue(allowed["ok"], allowed)

        guarded_cases = {
            "changes/slice-04-future/plan.md": "PATH_OUTSIDE_TASK_SCOPE",
            "docs/PROJECT_SPEC.md": "CORE_ARTIFACT_CHANGED",
            "pyproject.toml": "DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY",
            ".agents/skills/drone-slice-workflow/SKILL.md": (
                "FORBIDDEN_SLICE_PATH_CHANGED"
            ),
            "backend/rag/future.py": "FORBIDDEN_SLICE_PATH_CHANGED",
        }
        for changed_path, reason in guarded_cases.items():
            holder_case, repo_case = self.repo(slice_name="slice-03-target-resolution")
            self.addCleanup(holder_case.cleanup)
            base_case, snapshot_case = repo_case.snapshot(
                task_id="T03", changed_path=changed_path
            )
            git(repo_case.root, "switch", "--detach", snapshot_case)

            scoped = check(
                "S03-T03",
                repo_case.root,
                base_head=base_case,
                snapshot_head=snapshot_case,
            )

            self.assertFalse(scoped["ok"], changed_path)
            self.assertIn(reason, scoped["blocking_reasons"], changed_path)

    def test_workflow_s03_policy_identity_accepts_only_explicit_workflow_paths(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.workflow_policy_snapshot()
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("WORKFLOW-S03-POLICY", base, snapshot, repo.root)

        self.assertTrue(evidence["ok"], evidence)
        self.assertEqual(evidence["task"], "WORKFLOW-S03-POLICY")
        self.assertEqual(evidence["mode"], "task-review")
        self.assertEqual(evidence["scope"]["scope_kind"], "workflow-policy")
        self.assertEqual(evidence["risk_policy"]["effective_tier"], "HIGH")
        self.assertFalse(evidence["integration_authorized"])
        self.assertFalse(evidence["push_authorized"])
        self.assertFalse(evidence["human_approval"])

    def test_workflow_s03_policy_identity_rejects_extra_paths_and_wildcards(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.workflow_policy_snapshot(extra_path="README.md")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("WORKFLOW-S03-POLICY", base, snapshot, repo.root)

        self.assertFalse(evidence["ok"])
        self.assertIn(
            "PATH_OUTSIDE_WORKFLOW_POLICY_SCOPE", evidence["blocking_reasons"]
        )
        with self.assertRaises(Exception):
            immutable_evidence("WORKFLOW-S03-ANYTHING", base, snapshot, repo.root)
        with self.assertRaises(Exception):
            immutable_evidence("WORKFLOW-S04-POLICY", base, snapshot, repo.root)

    def test_workflow_s03_policy_identity_retains_protected_ref_rejection(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        git(repo.root, "switch", "main")
        base, snapshot = repo.workflow_policy_snapshot()

        evidence = immutable_evidence("WORKFLOW-S03-POLICY", base, snapshot, repo.root)

        self.assertFalse(evidence["ok"])
        self.assertIn("SNAPSHOT_ON_PROTECTED_BRANCH", evidence["blocking_reasons"])

    def test_workflow_s03_policy_identity_does_not_relax_regular_s03_task_scope(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.workflow_policy_snapshot()
        git(repo.root, "switch", "--detach", snapshot)

        task_evidence = immutable_evidence("S03-T07", base, snapshot, repo.root)

        self.assertFalse(task_evidence["ok"])
        self.assertIn("PATH_OUTSIDE_TASK_SCOPE", task_evidence["blocking_reasons"])

    def test_s03_public_contract_escalates_and_dependency_diff_fails_closed(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(
            task_id="T06", changed_path="backend/common/contracts.py"
        )
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("S03-T06", base, snapshot, repo.root)

        self.assertTrue(evidence["ok"], evidence)
        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "MEDIUM")
        self.assertEqual(evidence["risk_policy"]["effective_tier"], "HIGH")
        self.assertEqual(
            evidence["risk_policy"]["deterministic_escalation_paths"],
            ["backend/common/contracts.py"],
        )

        holder_dep, repo_dep = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder_dep.cleanup)
        base_dep, snapshot_dep = repo_dep.snapshot(
            task_id="T01", changed_path="uv.lock"
        )
        git(repo_dep.root, "switch", "--detach", snapshot_dep)
        dependency_scope = check(
            "S03-T01",
            repo_dep.root,
            base_head=base_dep,
            snapshot_head=snapshot_dep,
        )
        self.assertFalse(dependency_scope["ok"])
        self.assertIn(
            "DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY",
            dependency_scope["blocking_reasons"],
        )

    def test_s04_tasks_are_configured_in_order_and_high_risk_only(self) -> None:
        holder, repo = self.repo(slice_name="slice-04-variant-comparison")
        self.addCleanup(holder.cleanup)

        state = inspect(repo.root)

        self.assertEqual(
            [task["canonical_id"] for task in state["tasks"]],
            [
                "S04-T01",
                "S04-T02",
                "S04-T03",
                "S04-T04",
                "S04-T05",
                "S04-T06",
            ],
        )
        self.assertEqual(state["ordered_candidate"], "S04-T01")
        self.assertIsNone(state["executable_task"])
        self.assertEqual(state["low_batch"]["stop_reason"], "NON_LOW_RISK_BOUNDARY")
        self.assertEqual(state["low_batch"]["next_task"], "S04-T01")
        self.assertIn(
            "HIGH_RISK_HUMAN_DECISION_REQUIRED",
            state["tasks"][0]["execution_blockers"],
        )

        slice_authorized = inspect(repo.root, implementation_authorized_slice="S04")
        self.assertIsNone(slice_authorized["executable_task"])
        self.assertIn(
            "HIGH_RISK_HUMAN_DECISION_REQUIRED",
            slice_authorized["tasks"][0]["execution_blockers"],
        )

        task_authorized = inspect(repo.root, implementation_authorized_task="S04-T01")
        self.assertEqual(task_authorized["executable_task"], "S04-T01")
        for task in task_authorized["tasks"]:
            self.assertEqual(
                task["automation_policy"]["review_cadence"], "human-decision"
            )

    def test_s04_scope_accepts_planned_paths_and_rejects_forbidden_paths(self) -> None:
        allowed_cases = {
            "T01": "backend/conversation/comparison_set.py",
            "T02": "backend/catalog/variant_resolution.py",
            "T03": "backend/evidence/comparison_binding.py",
            "T04": "backend/shopify/dynamic_facts.py",
            "T05": "backend/application/variant_comparison.py",
            "T06": "tests/e2e/test_s04_comparison.py",
        }
        for task_id, changed_path in allowed_cases.items():
            holder, repo = self.repo(slice_name="slice-04-variant-comparison")
            self.addCleanup(holder.cleanup)
            base, snapshot = repo.snapshot(task_id=task_id, changed_path=changed_path)
            git(repo.root, "switch", "--detach", snapshot)

            scoped = check(
                f"S04-{task_id}",
                repo.root,
                base_head=base,
                snapshot_head=snapshot,
            )

            self.assertTrue(scoped["ok"], (task_id, changed_path, scoped))

        guarded_cases = {
            "docs/PROJECT_SPEC.md": "CORE_ARTIFACT_CHANGED",
            "changes/slice-03-target-resolution/tasks.md": (
                "FORBIDDEN_SLICE_PATH_CHANGED"
            ),
            "changes/slice-05-product-rag/tasks.md": "FORBIDDEN_SLICE_PATH_CHANGED",
            "changes/slice-06-evidence-recommendation/tasks.md": (
                "FORBIDDEN_SLICE_PATH_CHANGED"
            ),
            ".agents/skills/drone-slice-workflow/SKILL.md": (
                "FORBIDDEN_SLICE_PATH_CHANGED"
            ),
            "backend/rag/future.py": "FORBIDDEN_SLICE_PATH_CHANGED",
            "pyproject.toml": "DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY",
            "external/variant-id-staging/map.json": "PATH_OUTSIDE_TASK_SCOPE",
        }
        for changed_path, reason in guarded_cases.items():
            holder, repo = self.repo(slice_name="slice-04-variant-comparison")
            self.addCleanup(holder.cleanup)
            base, snapshot = repo.snapshot(task_id="T02", changed_path=changed_path)
            git(repo.root, "switch", "--detach", snapshot)

            scoped = check(
                "S04-T02",
                repo.root,
                base_head=base,
                snapshot_head=snapshot,
            )

            self.assertFalse(scoped["ok"], changed_path)
            self.assertIn(reason, scoped["blocking_reasons"], changed_path)

    def test_s04_public_contract_and_dependency_changes_fail_closed(self) -> None:
        holder, repo = self.repo(slice_name="slice-04-variant-comparison")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(
            task_id="T01", changed_path="backend/common/contracts.py"
        )
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("S04-T01", base, snapshot, repo.root)

        self.assertFalse(evidence["ok"])
        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "HIGH")
        self.assertEqual(evidence["risk_policy"]["effective_tier"], "HIGH")
        self.assertEqual(
            evidence["risk_policy"]["deterministic_escalation_paths"],
            ["backend/common/contracts.py"],
        )
        self.assertIn("PATH_OUTSIDE_TASK_SCOPE", evidence["blocking_reasons"])

        holder_dep, repo_dep = self.repo(slice_name="slice-04-variant-comparison")
        self.addCleanup(holder_dep.cleanup)
        base_dep, snapshot_dep = repo_dep.snapshot(
            task_id="T04", changed_path="uv.lock"
        )
        git(repo_dep.root, "switch", "--detach", snapshot_dep)
        dependency_scope = check(
            "S04-T04",
            repo_dep.root,
            base_head=base_dep,
            snapshot_head=snapshot_dep,
        )
        self.assertFalse(dependency_scope["ok"])
        self.assertIn(
            "DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY",
            dependency_scope["blocking_reasons"],
        )

    def test_s04_slice_review_uses_t06_union_scope_and_high_gate(self) -> None:
        holder, repo = self.repo(slice_name="slice-04-variant-comparison")
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T06"))
        changes = {
            "backend/conversation/comparison_set.py": "SET = 1\n",
            "backend/catalog/variant_resolution.py": "RESOLUTION = 1\n",
            "backend/evidence/comparison_binding.py": "EVIDENCE = 1\n",
            "backend/shopify/dynamic_facts.py": "DYNAMIC = 1\n",
            "backend/application/variant_comparison.py": "APP = 1\n",
            "tests/e2e/test_s04_comparison.py": "VALUE = 1\n",
            "eval/datasets/s04_matrix.json": "{}\n",
        }
        for relative, content in changes.items():
            path = repo.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S04): complete slice snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S04-T06", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertTrue(evidence["ok"], evidence)
        self.assertEqual(evidence["scope"]["scope_kind"], "slice-range")
        self.assertEqual(evidence["scope"]["completion_task"], "T06")
        self.assertEqual(
            evidence["scope"]["configured_tasks"],
            ["T01", "T02", "T03", "T04", "T05", "T06"],
        )
        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "HIGH")
        self.assertFalse(evidence["risk_policy"]["automation"]["auto_advance"])
        self.assertTrue(evidence["risk_policy"]["human_decision_required"])

        wrong_task = immutable_evidence(
            "S04-T05", base, snapshot, repo.root, mode="slice-review"
        )
        self.assertFalse(wrong_task["ok"])
        self.assertIn(
            "SLICE_REVIEW_TASK_IDENTITY_MISMATCH",
            wrong_task["blocking_reasons"],
        )

    def test_workflow_s04_policy_identity_accepts_only_workflow_paths(self) -> None:
        holder, repo = self.repo(slice_name="slice-04-variant-comparison")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.workflow_policy_snapshot()
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("WORKFLOW-S04-POLICY", base, snapshot, repo.root)

        self.assertTrue(evidence["ok"], evidence)
        self.assertEqual(evidence["task"], "WORKFLOW-S04-POLICY")
        self.assertEqual(evidence["scope"]["scope_kind"], "workflow-policy")
        self.assertEqual(evidence["risk_policy"]["effective_tier"], "HIGH")
        self.assertFalse(evidence["integration_authorized"])
        self.assertFalse(evidence["push_authorized"])

        extra_holder, extra_repo = self.repo(slice_name="slice-04-variant-comparison")
        self.addCleanup(extra_holder.cleanup)
        extra_base, extra_snapshot = extra_repo.workflow_policy_snapshot(
            extra_path="README.md"
        )
        git(extra_repo.root, "switch", "--detach", extra_snapshot)

        extra = immutable_evidence(
            "WORKFLOW-S04-POLICY", extra_base, extra_snapshot, extra_repo.root
        )
        self.assertFalse(extra["ok"])
        self.assertIn("PATH_OUTSIDE_WORKFLOW_POLICY_SCOPE", extra["blocking_reasons"])

    def test_s05_planned_table_is_nonexecutable_until_reconciled(self) -> None:
        holder, repo = self.repo(slice_name="slice-04-variant-comparison")
        self.addCleanup(holder.cleanup)
        repo.write_tasks(status_map(list(repo.titles), "T06"))
        planned = repo.root / "changes/slice-05-product-rag/tasks.md"
        planned.parent.mkdir(parents=True, exist_ok=True)
        planned.write_text(
            "| Planned Task | Title | Planned state | Dependencies |\n"
            "|---|---|---|---|\n"
            "| T01 | Document manifest and ingestion contract | PLANNED | "
            "Slice 4 completion + Slice 5 planning approval |\n"
            "| T02 | Scoped chunking and locator baseline | PLANNED | T01 |\n",
            encoding="utf-8",
        )

        state = inspect(repo.root, implementation_authorized_slice="S04")

        self.assertEqual(
            state["tasks_file"], "changes/slice-04-variant-comparison/tasks.md"
        )
        self.assertEqual(state["ready_tasks"], [])
        self.assertIsNone(state["selected_task"])
        self.assertIsNone(state["executable_task"])

    def test_s05_tasks_are_configured_but_require_formal_status_and_authority(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-05-product-rag")
        self.addCleanup(holder.cleanup)

        state = inspect(repo.root)

        self.assertEqual(
            [task["canonical_id"] for task in state["tasks"]],
            [
                "S05-T01",
                "S05-T02",
                "S05-T03",
                "S05-T04",
                "S05-T05",
                "S05-T06",
                "S05-T07",
            ],
        )
        self.assertEqual(state["ordered_candidate"], "S05-T01")
        self.assertIsNone(state["executable_task"])
        self.assertIn(
            "CURRENT_CONTEXT_IMPLEMENTATION_AUTHORIZATION_REQUIRED",
            state["tasks"][0]["execution_blockers"],
        )

        authorized = inspect(repo.root, implementation_authorized_slice="S05")
        self.assertEqual(authorized["executable_task"], "S05-T01")
        self.assertEqual(
            authorized["tasks"][0]["implementation_authorized_via"], "slice"
        )

    def test_s05_scope_keeps_rag_in_scope_and_agent_allowlist_precedence(self) -> None:
        allowed_cases = {
            "T01": "backend/rag/manifest.py",
            "T02": "backend/rag/chunking.py",
            "T03": "backend/rag/retriever.py",
            "T04": "tests/integration/test_s05_rag_quality.py",
            "T05": "backend/agent/rag_action_loop.py",
            "T06": "backend/agent/product_rag_answer.py",
            "T07": "eval/datasets/s05_matrix.json",
        }
        for task_id, changed_path in allowed_cases.items():
            holder, repo = self.repo(slice_name="slice-05-product-rag")
            self.addCleanup(holder.cleanup)
            base, snapshot = repo.snapshot(task_id=task_id, changed_path=changed_path)
            git(repo.root, "switch", "--detach", snapshot)

            scoped = check(
                f"S05-{task_id}",
                repo.root,
                base_head=base,
                snapshot_head=snapshot,
            )

            self.assertTrue(scoped["ok"], (task_id, changed_path, scoped))
            self.assertNotIn(
                changed_path, scoped["forbidden_slice_path_changes"], changed_path
            )

        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        t04_policy = policy["slices"]["changes/slice-05-product-rag/tasks.md"]["tasks"][
            "T04"
        ]
        self.assertIn("tests/integration/", t04_policy["allowed_paths"])
        self.assertEqual(
            t04_policy["verification_marker"], "unit or contract or integration"
        )

    def test_s05_semantic_action_rules_fail_closed_inside_allowed_paths(self) -> None:
        forbidden_cases = {
            ("T04", "backend/evidence/derived_evidence.py"): (
                "derived_evidence_recompute"
            ),
            ("T05", "backend/agent/commerce_refresh.py"): "refresh_commerce_state",
            ("T05", "backend/agent/open_web_retrieval.py"): "open_web_retrieval",
            ("T06", "backend/evidence/derived_evidence.py"): (
                "derived_evidence_recompute"
            ),
        }
        for (task_id, changed_path), behavior in forbidden_cases.items():
            holder, repo = self.repo(slice_name="slice-05-product-rag")
            self.addCleanup(holder.cleanup)
            base, snapshot = repo.snapshot(task_id=task_id, changed_path=changed_path)
            git(repo.root, "switch", "--detach", snapshot)

            scoped = check(
                f"S05-{task_id}",
                repo.root,
                base_head=base,
                snapshot_head=snapshot,
            )

            self.assertFalse(scoped["ok"], (task_id, changed_path, scoped))
            self.assertIn(
                "SEMANTIC_SLICE_ACTION_FORBIDDEN",
                scoped["blocking_reasons"],
                changed_path,
            )
            self.assertEqual(scoped["risk_policy"]["effective_tier"], "HIGH")
            self.assertIn(
                behavior,
                [item["behavior"] for item in scoped["semantic_action_violations"]],
                changed_path,
            )

    def test_s05_slice_review_rejects_forbidden_semantic_actions(self) -> None:
        holder, repo = self.repo(slice_name="slice-05-product-rag")
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        changes = {
            "backend/rag/retriever.py": "RETRIEVER = 1\n",
            "backend/agent/rag_action_loop.py": "AGENT = 1\n",
            "backend/evidence/derived_evidence.py": "DERIVED = 1\n",
            "tests/e2e/test_s05_product_rag.py": "VALUE = 1\n",
        }
        for relative, content in changes.items():
            path = repo.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S05): semantic violation")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S05-T07", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertFalse(evidence["ok"])
        self.assertIn(
            "SEMANTIC_SLICE_ACTION_FORBIDDEN",
            evidence["blocking_reasons"],
        )
        self.assertIn(
            "derived_evidence_recompute",
            [
                item["behavior"]
                for item in evidence["scope"]["semantic_action_violations"]
            ],
        )

    def test_s05_forbidden_dependency_and_core_artifact_changes_fail_closed(
        self,
    ) -> None:
        guarded_cases = {
            "docs/PROJECT_SPEC.md": "CORE_ARTIFACT_CHANGED",
            "pyproject.toml": "DEPENDENCY_FILE_CHANGED_WITHOUT_TASK_POLICY",
            "backend/catalog/hard_recheck.py": "FORBIDDEN_SLICE_PATH_CHANGED",
            "backend/shopify/refresh.py": "FORBIDDEN_SLICE_PATH_CHANGED",
            "backend/evaluation/rag_engine.py": "FORBIDDEN_SLICE_PATH_CHANGED",
            "changes/slice-06-evidence-recommendation/tasks.md": (
                "FORBIDDEN_SLICE_PATH_CHANGED"
            ),
            "storefront/product_rag.ts": "FORBIDDEN_SLICE_PATH_CHANGED",
        }
        for changed_path, reason in guarded_cases.items():
            holder, repo = self.repo(slice_name="slice-05-product-rag")
            self.addCleanup(holder.cleanup)
            base, snapshot = repo.snapshot(task_id="T03", changed_path=changed_path)
            git(repo.root, "switch", "--detach", snapshot)

            scoped = check(
                "S05-T03",
                repo.root,
                base_head=base,
                snapshot_head=snapshot,
            )

            self.assertFalse(scoped["ok"], changed_path)
            self.assertIn(reason, scoped["blocking_reasons"], changed_path)

    def test_s05_slice_review_uses_t07_union_scope_and_high_completion(self) -> None:
        holder, repo = self.repo(slice_name="slice-05-product-rag")
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        changes = {
            "backend/rag/manifest.py": "MANIFEST = 1\n",
            "backend/rag/chunking.py": "CHUNKING = 1\n",
            "backend/rag/retriever.py": "RETRIEVER = 1\n",
            "backend/evidence/rag_quality.py": "EVIDENCE = 1\n",
            "backend/agent/rag_action_loop.py": "AGENT = 1\n",
            "backend/application/product_rag.py": "APP = 1\n",
            "tests/e2e/test_s05_product_rag.py": "VALUE = 1\n",
            "eval/datasets/s05_matrix.json": "{}\n",
        }
        for relative, content in changes.items():
            path = repo.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S05): complete slice snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S05-T07", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertTrue(evidence["ok"], evidence)
        self.assertEqual(evidence["scope"]["scope_kind"], "slice-range")
        self.assertEqual(evidence["scope"]["completion_task"], "T07")
        self.assertEqual(
            evidence["scope"]["configured_tasks"],
            ["T01", "T02", "T03", "T04", "T05", "T06", "T07"],
        )
        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "HIGH")
        self.assertFalse(evidence["risk_policy"]["automation"]["auto_advance"])
        self.assertTrue(evidence["risk_policy"]["human_decision_required"])

        wrong_task = immutable_evidence(
            "S05-T06", base, snapshot, repo.root, mode="slice-review"
        )
        self.assertFalse(wrong_task["ok"])
        self.assertIn(
            "SLICE_REVIEW_TASK_IDENTITY_MISMATCH",
            wrong_task["blocking_reasons"],
        )

    def test_s05_policy_records_forbidden_actions_and_allowlist_precedence(
        self,
    ) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        slice_policy = policy["slices"]["changes/slice-05-product-rag/tasks.md"]

        self.assertEqual(slice_policy["completion_task"], "T07")
        self.assertTrue(slice_policy["activation_policy"]["formal_task_table_required"])
        self.assertTrue(
            slice_policy["activation_policy"]["planned_rows_non_executable"]
        )
        self.assertIn("backend/agent/", slice_policy["forbidden_path_prefixes"])
        self.assertIn("backend/agent/", slice_policy["tasks"]["T05"]["allowed_paths"])
        self.assertIn("backend/agent/", slice_policy["tasks"]["T06"]["allowed_paths"])
        self.assertIn(
            "Task allowed_paths are evaluated before forbidden_path_prefixes",
            slice_policy["scope_notes"]["allowlist_precedence"],
        )
        self.assertIn("backend/rag/", slice_policy["tasks"]["T03"]["allowed_paths"])
        self.assertNotIn("backend/rag/", slice_policy["forbidden_path_prefixes"])
        for action in (
            "refresh_commerce_state",
            "derived_evidence_recompute",
            "hard_eligibility_recheck",
            "open_web_retrieval",
            "shopify_write",
            "cross_product_retrieval",
            "more_than_two_total_action_rounds",
            "evidence_gate_weakening",
        ):
            self.assertIn(action, slice_policy["forbidden_actions"])

    def test_workflow_s05_policy_identity_accepts_only_workflow_paths(self) -> None:
        holder, repo = self.repo(slice_name="slice-05-product-rag")
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.workflow_policy_snapshot()
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("WORKFLOW-S05-POLICY", base, snapshot, repo.root)

        self.assertTrue(evidence["ok"], evidence)
        self.assertEqual(evidence["task"], "WORKFLOW-S05-POLICY")
        self.assertEqual(evidence["scope"]["scope_kind"], "workflow-policy")
        self.assertEqual(evidence["risk_policy"]["effective_tier"], "HIGH")
        self.assertFalse(evidence["integration_authorized"])
        self.assertFalse(evidence["push_authorized"])

        extra_holder, extra_repo = self.repo(slice_name="slice-05-product-rag")
        self.addCleanup(extra_holder.cleanup)
        extra_base, extra_snapshot = extra_repo.workflow_policy_snapshot(
            extra_path="README.md"
        )
        git(extra_repo.root, "switch", "--detach", extra_snapshot)

        extra = immutable_evidence(
            "WORKFLOW-S05-POLICY", extra_base, extra_snapshot, extra_repo.root
        )
        self.assertFalse(extra["ok"])
        self.assertIn("PATH_OUTSIDE_WORKFLOW_POLICY_SCOPE", extra["blocking_reasons"])

    def test_s03_task_review_requires_done_status(self) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        statuses = status_map(list(repo.titles))
        statuses["T01"] = "IN_PROGRESS"
        repo.write_tasks(statuses)
        (repo.root / "backend/common/contracts.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S03-T01): incomplete snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence("S03-T01", base, snapshot, repo.root)

        self.assertFalse(evidence["ok"])
        self.assertIn("TASK_NOT_DONE", evidence["blocking_reasons"])

    def test_s03_slice_review_uses_union_scope_and_completion_task(self) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        base = git(repo.root, "rev-parse", "HEAD")
        repo.write_tasks(status_map(list(repo.titles), "T07"))
        changes = {
            "backend/common/contracts.py": "CONTRACT = 1\n",
            "backend/conversation/reducer.py": "STATE = 1\n",
            "backend/catalog/alias_registry.py": "ALIAS = 1\n",
            "backend/application/target_fact.py": "APP = 1\n",
            "backend/agent/handoff.py": "HANDOFF = 1\n",
            "eval/datasets/s03_matrix.json": "{}\n",
            "tests/e2e/test_s03_journey.py": "VALUE = 1\n",
        }
        for relative, content in changes.items():
            path = repo.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-qm", "wip(S03): complete slice snapshot")
        snapshot = git(repo.root, "rev-parse", "HEAD")
        git(repo.root, "switch", "--detach", snapshot)

        evidence = immutable_evidence(
            "S03-T07", base, snapshot, repo.root, mode="slice-review"
        )

        self.assertTrue(evidence["ok"], evidence)
        self.assertEqual(evidence["scope"]["scope_kind"], "slice-range")
        self.assertEqual(evidence["scope"]["completion_task"], "T07")
        self.assertEqual(
            evidence["scope"]["configured_tasks"],
            ["T01", "T02", "T03", "T04", "T05", "T06", "T07"],
        )
        self.assertEqual(evidence["risk_policy"]["minimum_tier"], "HIGH")

        wrong_task = immutable_evidence(
            "S03-T06", base, snapshot, repo.root, mode="slice-review"
        )
        self.assertFalse(wrong_task["ok"])
        self.assertIn(
            "SLICE_REVIEW_TASK_IDENTITY_MISMATCH",
            wrong_task["blocking_reasons"],
        )

    def test_planned_high_risk_requires_human_decision(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        base, snapshot = repo.snapshot(
            task_id="T05", changed_path="backend/evidence/change.py"
        )
        git(repo.root, "switch", "--detach", snapshot)
        evidence = immutable_evidence("S02-T05", base, snapshot, repo.root)
        verification = successful_verification("S02-T05", base, snapshot)
        with patch("verify_commit_readiness.verify_task", return_value=verification):
            result = checkpoint_readiness(
                "S02-T05",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                reviewed_risk_tier="HIGH",
            )
        self.assertFalse(result["ok"])
        self.assertTrue(result["human_approval_required"])
        self.assertIn("HIGH_RISK_HUMAN_DECISION_REQUIRED", result["blocking_reasons"])
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
            reviewed_risk_tier="LOW",
        )
        self.assertEqual(low["workflow_stage"], "BLOCKED")
        self.assertEqual(low["status"], "CHECKPOINT_NOT_READY")
        self.assertIn(
            "REVIEWED_RISK_TIER_BELOW_POLICY_MINIMUM",
            low["blocking_reasons"],
        )

        verification = successful_verification("S02-T01", base, snapshot)
        with patch("verify_commit_readiness.verify_task", return_value=verification):
            high = checkpoint_readiness(
                "S02-T01",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=evidence["digest"],
                reviewed_risk_tier="HIGH",
            )
        self.assertEqual(high["workflow_stage"], "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(high["status"], "HUMAN_DECISION_REQUIRED")
        self.assertIn("HIGH_RISK_HUMAN_DECISION_REQUIRED", high["blocking_reasons"])
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
        if ready.returncode == 0:
            self.assertEqual(ready_payload["workflow_stage"], "AUTO_ADVANCE_ELIGIBLE")
            self.assertEqual(ready_payload["status"], "AUTO_ADVANCE_ELIGIBLE")
            self.assertTrue(ready_payload["auto_advance"])
        else:
            self.assertEqual(ready.returncode, 1)
            self.assertEqual(ready_payload["workflow_stage"], "BLOCKED")
            self.assertEqual(ready_payload["status"], "CHECKPOINT_NOT_READY")
            self.assertIn(
                "TARGETED_VERIFICATION_FAILED",
                ready_payload["blocking_reasons"],
            )
            self.assertFalse(ready_payload["auto_advance"])
        self.assertFalse(ready_payload["checkpoint_accepted"])
        self.assertFalse(ready_payload["integration_authorized"])
        self.assertFalse(ready_payload["push_authorized"])

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
            self.assertEqual(execution_policy["review"], "boundary-and-slice")
            self.assertEqual(
                execution_policy["review_cadence"],
                {
                    "LOW": {
                        "review": "batch-or-slice-completion",
                        "max_tasks_per_invocation": 3,
                    },
                    "MEDIUM": {"review": "task"},
                    "HIGH": {"review": "human-decision"},
                },
            )
            self.assertEqual(
                execution_policy["task_validation"],
                {
                    "lint": "changed-python-files",
                    "lock_check": "slice-completion-or-dependency-change",
                },
            )
            if "delivery" in execution_policy:
                self.assertEqual(
                    execution_policy["delivery"],
                    "feature-delivery-proposed-non-operational",
                )
            self.assertEqual(
                execution_policy["automation"],
                {
                    "auto_advance": True,
                    "human_gate": "unplanned-exception",
                    "review_required": True,
                    "verification_mode": "targeted",
                },
            )
            for task_policy in slice_policy["tasks"].values():
                self.assertNotIn("checkpoint_policy", task_policy)

    def test_low_batch_hard_limits_one_invocation_and_stops_at_risk_boundary(
        self,
    ) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        policy_path = (
            repo.root
            / ".agents/skills/drone-slice-workflow/references/task-scope-policy.json"
        )
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        slice_policy = policy["slices"][
            repo.tasks_path.relative_to(repo.root).as_posix()
        ]
        for task_id in ("T01", "T02", "T03", "T04"):
            repo.dependencies[task_id] = "SATISFIED"
            slice_policy["tasks"][task_id]["risk_tier"] = "LOW"
        slice_policy["tasks"]["T05"]["risk_tier"] = "MEDIUM"
        repo.write_tasks(status_map(list(repo.titles)))
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        state = inspect(repo.root, implementation_authorized_slice="S02")
        self.assertEqual(state["low_batch"]["tasks"], ["S02-T01", "S02-T02", "S02-T03"])
        self.assertEqual(state["low_batch"]["stop_reason"], "LOW_BATCH_LIMIT_REACHED")
        self.assertEqual(state["low_batch"]["next_task"], "S02-T04")

        slice_policy["tasks"]["T03"]["risk_tier"] = "MEDIUM"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        state = inspect(repo.root, implementation_authorized_slice="S02")
        self.assertEqual(state["low_batch"]["tasks"], ["S02-T01", "S02-T02"])
        self.assertEqual(state["low_batch"]["stop_reason"], "NON_LOW_RISK_BOUNDARY")

    def test_medium_boolean_cannot_unlock_without_bound_reviewer_evidence(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        repo.snapshot(task_id="T01")
        base, snapshot = repo.snapshot(
            task_id="T02", changed_path="backend/conversation/change.py"
        )
        git(repo.root, "switch", "--detach", snapshot)
        immutable = immutable_evidence("S02-T02", base, snapshot, repo.root)
        verification = successful_verification("S02-T02", base, snapshot)
        with patch("verify_commit_readiness.verify_task", return_value=verification):
            blocked = checkpoint_readiness(
                "S02-T02",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=immutable["digest"],
                reviewed_risk_tier="MEDIUM",
            )
        self.assertFalse(blocked["ok"])
        self.assertIn("REVIEWER_EVIDENCE_REQUIRED", blocked["blocking_reasons"])
        with patch("verify_commit_readiness.verify_task", return_value=verification):
            ready = checkpoint_readiness(
                "S02-T02",
                repo.root,
                base_revision=base,
                snapshot_revision=snapshot,
                reviewed_digest=immutable["digest"],
                reviewed_risk_tier="MEDIUM",
                reviewer_evidence=reviewer_evidence(immutable),
            )
        self.assertTrue(ready["ok"])

    def test_scheduler_serializes_multiple_ready_s03_tasks(self) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        _, snapshot = repo.snapshot(
            task_id="T01", changed_path="backend/conversation/change.py"
        )
        git(repo.root, "switch", "--detach", snapshot)

        unauthorised = inspect(repo.root)
        self.assertEqual(unauthorised["ready_tasks"], ["S03-T02", "S03-T03"])
        self.assertEqual(unauthorised["selected_task"], "S03-T02")
        self.assertIsNone(unauthorised["executable_task"])

        authorised = inspect(repo.root, implementation_authorized_slice="S03")
        self.assertEqual(authorised["selected_task"], "S03-T02")
        self.assertIsNone(authorised["executable_task"])
        self.assertIn(
            "HIGH_RISK_HUMAN_DECISION_REQUIRED",
            next(item for item in authorised["tasks"] if item["id"] == "T02")[
                "execution_blockers"
            ],
        )
        self.assertFalse(
            next(item for item in authorised["tasks"] if item["id"] == "T03")[
                "executable"
            ]
        )

    def test_scheduler_advances_by_table_order_without_changing_dependencies(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        repo.snapshot(task_id="T01", changed_path="backend/conversation/t01.py")
        _, snapshot = repo.snapshot(
            task_id="T02", changed_path="backend/conversation/t02.py"
        )
        git(repo.root, "switch", "--detach", snapshot)
        state = inspect(repo.root, implementation_authorized_slice="S03")
        self.assertEqual(state["selected_task"], "S03-T03")
        self.assertEqual(state["executable_task"], "S03-T03")
        self.assertNotIn("S03-T04", state["ready_tasks"])

    def test_scheduler_rejects_cycles_unknown_dependencies_and_duplicate_ids(
        self,
    ) -> None:
        holder, repo = self.repo(slice_name="slice-03-target-resolution")
        self.addCleanup(holder.cleanup)
        repo.dependencies["T01"] = "T02"
        repo.write_tasks(status_map(list(repo.titles)))
        cycle = inspect(repo.root)
        self.assertIn("DEPENDENCY_CYCLE", cycle["blocking_reasons"])
        self.assertIsNone(cycle["selected_task"])
        self.assertIsNone(cycle["executable_task"])

        repo.dependencies["T01"] = "T99"
        repo.write_tasks(status_map(list(repo.titles)))
        unknown = inspect(repo.root)
        self.assertIn("UNKNOWN_DEPENDENCY", unknown["blocking_reasons"])
        self.assertIsNone(unknown["selected_task"])
        self.assertIsNone(unknown["executable_task"])

        repo.tasks_path.write_text(
            repo.tasks_path.read_text(encoding="utf-8")
            + "| T01 | duplicate | NOT_STARTED | SATISFIED |\n",
            encoding="utf-8",
        )
        with self.assertRaises(Exception):
            inspect(repo.root)

    def test_task_local_automation_authority_fails_closed(self) -> None:
        holder, repo = self.repo()
        self.addCleanup(holder.cleanup)
        policy_path = (
            repo.root
            / ".agents/skills/drone-slice-workflow/references/task-scope-policy.json"
        )
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["slices"][repo.tasks_path.relative_to(repo.root).as_posix()]["tasks"][
            "T01"
        ]["automation"] = {
            "auto_advance": False,
            "human_gate": "task",
            "review_required": True,
            "verification_mode": "targeted",
        }
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        result = check("S02-T01", repo.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "CONFLICTING_TASK_AUTOMATION_AUTHORITY")


if __name__ == "__main__":
    unittest.main()
