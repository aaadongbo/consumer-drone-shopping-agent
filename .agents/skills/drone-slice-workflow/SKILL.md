---
name: drone-slice-workflow
description: "Manage the ordered Slice task workflow for this consumer-drone shopping-agent repository: inspect status, run one authorized Task, create a local snapshot, independently review it, prepare Human-required checkpoint evidence, review Slice completion, or perform Human-approved integration. Use only for this repository's Slice workflow."
---

# Drone Slice Workflow

Use one mode: `status`, `run-next`, `snapshot`, `review`, `checkpoint`, `slice-review`, `integrate-approved`, or `reconcile`. If invocation is implicit or the user only says “继续”, start with `status`; discovery never authorizes a write, Task execution, status change, snapshot, checkpoint, integration, merge, or push.

## Sources and state

Treat `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, the active Slice `plan.md`, and `tasks.md` as the sources of truth. Git/worktrees, the current diff, the Task status table, and each existing Execution Record jointly express state; do not create another status file.

Formal Task states are `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, and `DONE`. Derived stages are reported from Git, policy, and current-context evidence and are not persisted. A WIP snapshot is immutable local review input. An AI verdict, Human approval, checkpoint readiness, integration/merge, and push are distinct authorities.

## Mode routing

- `status`: run `scripts/inspect_state.py` and report every Task, the unique ordered candidate, current-context authority, executable Task, dependencies, worktrees, and blockers. An ordered candidate is not executable until the fixed implementation gate and current-context authority both pass.
- `run-next`: read [references/execution-protocol.md](references/execution-protocol.md), execute exactly one uniquely executable authorized Task, run its gates, update only its existing Task record, and stop before another Task.
- `snapshot`: after the Task is `DONE` and deterministic gates pass, create exactly one Task-scoped local WIP commit. It must be detached or on a task branch, never on a protected integration branch; stop after immutable evidence. A `SNAPSHOT_CREATED` result must carry `integration_authorized: false`, `push_authorized: false`, and `human_approval: false`. A snapshot is not acceptance, integration, merge, Human approval, or push.
- `review`: in an independent clean Session/Worktree, inspect only `base_head..snapshot_head`, recompute the digest, and output one leading verdict: `AI_REVIEW_PASS`, `AI_REVIEW_NEEDS_CHANGES`, or `BLOCKED`. Task review evidence requires that exact Task to be `DONE`; `IN_PROGRESS` fails closed. A pass wording is `AI_REVIEW_PASS — Awaiting explicit Human approval`.
- `checkpoint`: run `verify_commit_readiness.py` for identity, scope, digest, and current Human-required status. Missing, invalid, or mismatched evidence reports `BLOCKED / CHECKPOINT_NOT_READY`; only complete matching evidence with `AI_REVIEW_PASS` and a valid sufficient reviewed risk tier may report `HUMAN_APPROVAL_REQUIRED`. It never accepts a checkpoint or authorizes integration/push; `--verification-pass` is ignored.
- `slice-review`: after every Slice Task is `DONE`, independently review the complete Slice range against the union of every configured Task scope. The Task identity must equal the policy's explicit `completion_task`. Core Artifact, dependency, forbidden-path, identity, and aggregate HIGH-risk gates still apply. Stop for the Human merge/push decision.
- `integrate-approved`: proceed only when the current user explicitly authorizes the exact integration/merge or local integration commit. Push requires a separate explicit authorization.
- `reconcile`: read [references/reconciliation-rules.md](references/reconciliation-rules.md) and remain read-only unless the applicable authority is explicit.

## Deterministic helpers

Run helpers from the repository root with the repository Python:

```text
python .agents/skills/drone-slice-workflow/scripts/inspect_state.py [--authorize-task S02-T01] [--approved-workflow-oid <human-approved-oid>]
python .agents/skills/drone-slice-workflow/scripts/check_scope.py T06
python .agents/skills/drone-slice-workflow/scripts/verify_task.py T06
python .agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py S02-T01 --evidence --base-head <oid> --snapshot-head <oid> --mode task-review
python .agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py S02-T01 --checkpoint --base-head <oid> --snapshot-head <oid> --reviewed-digest <sha256> --ai-review-pass --risk-tier MEDIUM
```

Treat JSON `ok: false`, any nonzero result, identity/scope/digest mismatch, ambiguous Task, dirty unrelated path, core Artifact change, unauthorized dependency, or extra path as a failed gate. An unconfigured Slice or Task fails closed. Record only commands actually run and their real exit codes.

The fixed schema/marker and baseline gate prevent a detached or self-reported Workflow change from unlocking S02-T01. Only a matching integrated baseline on a protected ref, or one exact current-context Human-approved baseline OID, can satisfy that gate. `main`, `master`, and their remote-tracking forms are always protected; policy may add patterns but cannot remove them.

Risk tiers are `LOW`, `MEDIUM`, and `HIGH`. LOW/MEDIUM may reach snapshot and independent review, but never become an automatic checkpoint. HIGH requires explicit Human authority. Public Contract, Product Behavior, Architecture, Acceptance, Accepted Decision, major/cross-Slice dependency, external service behavior, Shopify writes, or safety-gate weakening are HIGH or escalation regardless of path.

## Minimal safety boundary

This workflow intentionally does not provide transaction-level concurrent Git-ref protection, protected-ref ancestry/TOCTOU auditing, temporary verification artifacts, or automatic checkpoint acceptance. Safety comes from refusing protected-branch snapshots, binding review to an immutable range and digest, keeping checkpoint status Human-required, and requiring Human-controlled integration and push.

本版本不提供并发 Git ref 的事务级保护。安全边界通过禁止 protected-branch snapshot、禁止自动 checkpoint acceptance、以及 Human-controlled integration 保证。

Stop when authority, dependencies, Acceptance, scope, evidence, or review are insufficient. `AI_REVIEW_NEEDS_CHANGES` requires a new snapshot and digest; previous evidence is invalid. Never stage, alter, or repair another Session's files.
