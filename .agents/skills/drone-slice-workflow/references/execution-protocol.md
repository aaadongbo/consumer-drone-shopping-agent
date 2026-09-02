# Execution Protocol

## Common readiness

1. Resolve repository root, HEAD, branch/detached state, current `git status --short`, and same-Slice activity in other worktrees.
2. At Slice start, a Human escalation, and Slice completion, read the full source-of-truth set. For an ordinary Task, read the active plan/tasks, its execution record, relevant code/tests, and the current diff; do not reread unrelated core artifacts.
3. Run `inspect_state.py`. It reports all dependency-ready `ready_tasks` and a single stable task-table-order `selected_task`. Only a valid Slice authorization plus the fixed baseline gate can make that selected Task executable.
4. Stop for pre-existing unrelated changes, multiple active Tasks, unmet dependencies/entry gates, an unconfigured policy, or same-Slice activity in another worktree. Never mutate another worktree.
5. Record the implementation base and pre-existing diff before any authorized write.

## `run-next`

Run the selected Task without crossing a scope or safety gate. A valid Slice authorization (`inspect_state.py --authorize-slice S02`) covers the approved planned Task set. Treat `inspect_state.py`'s `low_batch` as the only LOW batch authority: execute only its listed rows, at most three currently dependency-ready adjacent LOW Tasks, and stop the invocation at its explicit `LOW_BATCH_LIMIT_REACHED` or risk/not-ready boundary. Never carry a count into another invocation. LOW Tasks run changed-path scope, changed-Python lint, and changed test files when present (otherwise the policy-selected test marker). MEDIUM Tasks add an immutable snapshot and independent-child reviewer JSON before continuing. HIGH Tasks and any escalation stop for a current-context Human decision. Select the next ready Task by task-table order in the same Slice Implementation Session. Always mark only the current Task `IN_PROGRESS`/`DONE`, keep one Task active at a time, record real commands and exit codes, and stop on a dependency change, scope mismatch, or review/evidence failure.

## `snapshot`

A snapshot is one local WIP commit for an immutable boundary review, never acceptance or integration authority. LOW Tasks do not create an intermediate snapshot unless they reach their three-Task handoff boundary; MEDIUM Tasks, escalations, and Slice completion do.

1. Require `DONE`, passing deterministic gates, exact Task-scoped paths, and no unrelated residue.
2. Refuse a snapshot on `main`, `master`, configured protected refs, or a commit already directly held by a protected ref. A task branch or detached checkout is valid. Policy cannot remove the built-in protections.
3. Stage only exact Task paths, inspect the complete cached diff, create one canonical WIP commit, and do not amend an existing reviewed snapshot.
4. Require clean `HEAD == snapshot_head` and `base_head` as an ancestor of `snapshot_head`.
5. Emit `verify_commit_readiness.py ... --evidence` with canonical Slice/Task, base, snapshot, mode, changed paths, file type/mode, content-bound digest, risk, verification results, and known limits. Hand this immutable input to a separate reviewer.

## `review`

The reviewer is a fresh independent child in a separate clean detached Worktree at the exact `snapshot_head`; it recomputes immutable evidence, makes no writes, and inspects only `base_head..snapshot_head` plus the applicable Acceptance and actual verification records. For a MEDIUM pass, write a JSON summary with schema version, `AI_REVIEW_PASS`, Slice/Task/base/snapshot/mode/digest, reviewer identity and session, `kind: independent-child`, detached/clean review-worktree state, `no_write: true`, empty findings, and every actual verification command with exit code and result. Task-review evidence requires the selected MEDIUM Task to be strictly `DONE`; `IN_PROGRESS` fails closed. Any missing/malformed field or identity, path, mode/type, content, digest, cleanliness, or no-write mismatch fails closed. Fixes require a new snapshot/digest.

## `checkpoint`

`verify_commit_readiness.py --checkpoint` is a routing handoff for an immutable boundary, never a direct protected-branch acceptance operation. For MEDIUM it accepts only the complete reviewer JSON schema via `--review-evidence`, validates every binding against immutable identity/scope/digest, and reruns policy-selected verification against that exact snapshot. Boolean flags, inline prose, and caller claims are not evidence. Missing, invalid, mismatched, non-independent, writable, or plan-only evidence reports `BLOCKED / CHECKPOINT_NOT_READY`. Complete matching MEDIUM evidence may report `AUTO_ADVANCE_ELIGIBLE`; this only permits the next selected planned implementation Task under a valid Slice authorization. HIGH or actual Product Behavior, Architecture, public Contract, major dependency, external service, Shopify write, or safety change routes to `HUMAN_DECISION_REQUIRED`; no route authorizes direct main integration.

## `slice-review` and `integrate-approved`

After every configured Slice Task is `DONE`, run the full suite and independently review the complete Slice range using the union of all configured Task scopes. The supplied Task must exactly match the policy's explicit `completion_task`; any other Task identity fails closed. The formal Task-status table must parse cleanly, and a tasks-table-only completion range fails closed: the range must also contain implementation-scope changes. Continue to reject core Artifact changes, unauthorized dependencies, forbidden paths, identity mismatches, and aggregate HIGH-risk conditions. Direct integration or local main commits require explicit current-context Human authorization for the exact range and target.

## `feature-delivery` proposal

`feature-delivery` is proposed/non-operational in this planning diff. It must not be invoked as a mode and must not alter `integrate-approved`, checkpoint routing, or LOW/MEDIUM/HIGH Task gates. A later Workflow Implementation Planning pass must define and test feature branch push, PR-only main protection, required `quality` checks, force-push prevention, repository-managed auto-merge, Slice completion evidence, and failure gates before any session can rely on it.

This repository may contain roadmap text for this target mode before external GitHub settings and enforcement code are active. Do not claim feature delivery, CI, branch protection, or auto-merge is configured merely because the files exist. Even after implementation, feature delivery may automate only post-Slice PR/CI/merge mechanics; it cannot make MEDIUM/HIGH Tasks skip their required Human gates.

## Verification and human summary

Each Task runs changed-path scope, relevant lint, and targeted verification selected by policy. Lock checks, full-repository lint, and the full suite are reserved for Slice completion, unless a dependency, public Contract, external service, Shopify write, or security/safety change requires an earlier escalation. Human-facing output is a compact digest: Task/Slice, risk and gate, changed paths, Acceptance result, targeted/full test counts, first failures and fixes, AI verdict, immutable digest when one exists, branch/PR state when applicable, and next action. Do not repeat raw command logs unless a failure or escalation needs them.
