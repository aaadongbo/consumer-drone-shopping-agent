---
name: drone-slice-workflow
description: "Manage the ordered Slice task workflow for this consumer-drone shopping-agent repository: inspect status, run the next authorized task, review its uncommitted diff, prepare an explicitly approved local commit, or reconcile implementation/design conflicts. Use only for this repository's Slice plan/tasks workflow, not for general coding questions or unrelated edits."
---

# Drone Slice Workflow

Use one mode: `status`, `run-next`, `review`, `commit-approved`, or `reconcile`. If invocation is implicit or the user only says “继续”, start with `status`; implicit discovery never authorizes a write, Task execution, status change, commit, or push.

## Sources and state

Treat `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, the active Slice `plan.md`, and `tasks.md` as the sources of truth. Git/worktrees, the current diff, Task status table, and Execution Record jointly express state; do not create another state file.

Formal Task states remain `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, and `DONE`. Workflow stages may progress through `AI_REVIEW_PASS`, `HUMAN_APPROVAL_REQUIRED`, `COMMIT_READY`, and `COMMITTED` without extending that enum. Only verified Acceptance permits `DONE`; only the user can supply Human approval.

## Mode routing

- `status`: run `scripts/inspect_state.py`, read plan/tasks, report every Task, the unique legal next Task, dependencies, active worktrees, and blockers. Make no changes.
- `run-next`: read [references/execution-protocol.md](references/execution-protocol.md), then execute exactly one uniquely legal Task authorized by this invocation. Run the scripts and gates prescribed there. Stop after AI review for Human feedback; do not commit or start another Task.
- `review`: read [references/review-checklist.md](references/review-checklist.md), independently review the complete uncommitted Task diff, and output exactly one leading verdict: `AI_REVIEW_PASS`, `AI_REVIEW_NEEDS_CHANGES`, or `BLOCKED`. A pass must say `AI_REVIEW_PASS — Awaiting explicit Human approval` and include the normalized Task ID, base HEAD, and staging-invariant complete diff SHA-256 from `verify_commit_readiness.py <Task> --hash-only`. Never claim Human approval.
- `commit-approved`: read the commit section of [references/execution-protocol.md](references/execution-protocol.md). Proceed only when the current user message explicitly authorizes the current Task’s local commit. Re-run gates, stage only approved Task paths, run `scripts/verify_commit_readiness.py` with the reviewed diff hash and current-context approval flag, inspect the full cached diff, commit locally, verify the worktree, and stop. Never push or start the next Task.
- `reconcile`: read [references/reconciliation-rules.md](references/reconciliation-rules.md). Default to a read-only Discovery/impact/classification/recommendation report. Do not change Product Spec, Architecture, Decisions, plan, Contract, or Acceptance without explicit authority.

## Deterministic helpers

Run helpers from the repository root with the repository Python; they use only the standard library.

- `python .agents/skills/drone-slice-workflow/scripts/inspect_state.py`
- `python .agents/skills/drone-slice-workflow/scripts/check_scope.py T06`
- `python .agents/skills/drone-slice-workflow/scripts/verify_task.py T06`
- `python .agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py T06 --reviewed-head <oid> --reviewed-diff-sha256 <sha256> --ai-review-pass --human-approved [--dependency-review-confirmed]`

Treat JSON `ok: false`, any nonzero command result, Task/snapshot mismatch, ambiguous active/next Task, dirty unrelated paths, core Artifact changes, unauthorized dependency changes, or extra staged paths as a failed gate. `check_scope.py` reads [references/task-scope-policy.json](references/task-scope-policy.json) for the active Slice; an unconfigured Slice or Task fails closed. A plan-authorized dependency diff requires both manual proof that it is minimal and Task-local and the conditional commit-gate flag `--dependency-review-confirmed`; major or cross-Slice dependencies require Human escalation. `CURRENT_WORKTREE_DIRTY` is expected only after the authorized Task begins and only when scope validation proves every path belongs to that Task.

## Authority and stop conditions

Protect the current checkout and all other worktrees. Never stage, move, commit, or repair another Session’s files. Stop before work when the current checkout contains pre-existing unrelated changes. Other dirty worktrees are reported and isolated, not automatically treated as current-worktree contamination.

Stop and await the user when the legal Task is ambiguous, dependencies are unmet, Acceptance is unmet, review needs changes, authorization is missing, scope is exceeded, a public Contract/Product/Architecture/Accepted Decision conflict appears, or a required gate fails after bounded diagnosis. Commit authority is not push authority; push is prohibited by default.
