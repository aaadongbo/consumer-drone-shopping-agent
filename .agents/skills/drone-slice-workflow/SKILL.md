---
name: drone-slice-workflow
description: "Manage the lightweight Slice task workflow for this consumer-drone shopping-agent repository: inspect status, run one authorized Task at a time, apply targeted or Slice-completion verification, review immutable boundaries, and perform Human-approved integration. Use only for this repository's Slice workflow."
---

# Drone Slice Workflow

Use one mode: `status`, `run-next`, `snapshot`, `review`, `checkpoint`, `slice-review`, `integrate-approved`, or `reconcile`. `feature-delivery` is a proposed/non-operational protocol note, not an executable mode. If invocation is implicit or the user only says “继续”, start with `status`; discovery never authorizes a write, Task execution, status change, snapshot, checkpoint, integration, merge, or push.

## Sources and state

Treat `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, the active Slice `plan.md`, and `tasks.md` as the sources of truth. Git/worktrees, the current diff, the Task status table, and each existing Execution Record jointly express state; do not create another status file.

Freeze this Skill during an active Slice. A workflow change needs a separately authorized governance session and a demonstrated blocker; it never rides along with business work.

Formal Task states are `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, and `DONE`. Derived stages are reported from Git, policy, and current-context evidence and are not persisted. A WIP snapshot is immutable local review input. An AI verdict, Human approval, checkpoint readiness, integration/merge, and push are distinct authorities.

## Mode routing

- `status`: run `scripts/inspect_state.py` and report `ready_tasks`, the stable table-order `selected_task`, current-context authority, executable Task, dependencies, worktrees, and blockers. Multiple ready DAG Tasks are valid; only the selected Task can become executable.
- `run-next`: read [references/execution-protocol.md](references/execution-protocol.md). A valid Slice authorization covers only its approved planned Task set. A scheduler `low_batch` is one invocation only: it contains no more than three currently dependency-ready adjacent LOW Tasks and must stop when it returns `LOW_BATCH_LIMIT_REACHED`; it has no cross-call counter. MEDIUM Tasks add an immutable snapshot and fresh independent-child reviewer JSON. HIGH Tasks stop for Human. Select the next ready Task by table order. Never run two Tasks concurrently; stop for an escalation, invalid evidence, scope mismatch, or exhausted repair budget.
- `snapshot`: create an immutable WIP commit only at a MEDIUM/risk boundary, a LOW handoff, or Slice completion. It must be detached or on a task branch, never on a protected integration branch. A snapshot is not acceptance, integration, merge, Human approval, or push.
- `review`: in an independent clean Session/Worktree, inspect the exact immutable boundary range, recompute the digest, and output one leading verdict: `AI_REVIEW_PASS`, `AI_REVIEW_NEEDS_CHANGES`, or `BLOCKED`. Task review requires that MEDIUM Task to be `DONE`; Slice review requires the completion Task and full Slice range. A pass does not authorize integration or push.
- `checkpoint`: applies to an immutable MEDIUM/risk/Slice boundary. A MEDIUM boundary requires `--review-evidence <review.json>` with the fixed independent-child schema: PASS verdict, risk tier, Slice/Task/base/snapshot/mode/digest binding, reviewer identity/session, detached clean review worktree at the snapshot, `no_write: true`, empty findings, and real successful command results. Booleans, prose, and caller-supplied risk/digest claims cannot substitute for that file. Complete matching evidence with real verification may report `AUTO_ADVANCE_ELIGIBLE` only for MEDIUM; this never accepts, integrates, or pushes.
- `slice-review`: after every Slice Task is `DONE`, independently review the complete Slice range against the union of every configured Task scope. The Task identity must equal the policy's explicit `completion_task`. Core Artifact, dependency, forbidden-path, identity, and aggregate HIGH-risk gates still apply. Stop for the Human merge/push decision.
- `integrate-approved`: proceed only when the current user explicitly authorizes the exact integration/merge or local integration commit. Direct protected-branch push remains forbidden.
- `feature-delivery` proposal: planned/non-operational protocol for future Slice automation. It is not callable through this Skill and must not be treated as active enforcement. A separate Workflow Implementation Planning and Human approval must define and test feature branch push, PR creation, required CI, force-push prevention, auto-merge authorization, and Slice completion evidence before any operation can rely on it. Even then, it may automate only post-Slice PR/CI/merge mechanics and must not weaken LOW/MEDIUM/HIGH Task gates.
- `reconcile`: read [references/reconciliation-rules.md](references/reconciliation-rules.md) and remain read-only unless the applicable authority is explicit.

## Deterministic helpers

Run helpers from the repository root with the repository Python:

```text
python .agents/skills/drone-slice-workflow/scripts/inspect_state.py [--authorize-task S02-T01] [--approved-workflow-oid <human-approved-oid>]
python .agents/skills/drone-slice-workflow/scripts/check_scope.py T06
python .agents/skills/drone-slice-workflow/scripts/verify_task.py T06
python .agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py S02-T01 --evidence --base-head <oid> --snapshot-head <oid> --mode task-review
python .agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py S02-T02 --checkpoint --base-head <oid> --snapshot-head <oid> --reviewed-digest <sha256> --risk-tier MEDIUM --review-evidence <review.json>
```

Treat JSON `ok: false`, any nonzero result, identity/scope/digest mismatch, ambiguous Task, dirty unrelated path, core Artifact change, unauthorized dependency, or extra path as a failed gate. An unconfigured Slice or Task fails closed. Record only commands actually run and their real exit codes.

The fixed schema/marker and baseline gate prevent a detached or self-reported Workflow change from unlocking S02-T01. Only a matching integrated baseline on a protected ref, or one exact current-context Human-approved baseline OID, can satisfy that gate. `main`, `master`, and their remote-tracking forms are always protected; policy may add patterns but cannot remove them.

Risk tiers are `LOW`, `MEDIUM`, and `HIGH`:

- LOW: targeted verification only; `low_batch.tasks` holds at most three currently-ready adjacent Tasks for one invocation. Review is deferred to the next MEDIUM/handoff boundary or Slice completion.
- MEDIUM: targeted verification, immutable Task snapshot, and fresh schema-valid independent-child review evidence; a matching pass continues the approved Slice automatically.
- HIGH: immediately stop for a current-context Human decision before implementation or any review handoff.

Full-suite checks, independent Slice review, and delivery CI belong at Slice completion or PR time. All tiers retain scope checks, fail-closed errors, and no direct protected-branch integration. Public Contract, Product Behavior, Architecture, Acceptance, Accepted Decision, major/cross-Slice dependency, external service behavior, Shopify writes, or safety-gate weakening are immediate Human escalation regardless of configured path.

## Minimal safety boundary

This workflow intentionally does not provide transaction-level concurrent Git-ref protection, protected-ref ancestry/TOCTOU auditing, temporary verification artifacts, or direct protected-branch checkpoint acceptance. Safety comes from refusing protected-branch snapshots, binding review to an immutable range and digest, requiring independent AI Review, escalating by risk tier, and keeping feature-delivery non-operational until separately implemented and approved.

本版本不提供并发 Git ref 的事务级保护。安全边界通过禁止 protected-branch snapshot、禁止自动 checkpoint acceptance、以及 Human-controlled integration 保证。

Stop when authority, dependencies, Acceptance, scope, evidence, or review are insufficient. `AI_REVIEW_NEEDS_CHANGES` requires a new snapshot and digest; previous evidence is invalid. Never stage, alter, or repair another Session's files.
