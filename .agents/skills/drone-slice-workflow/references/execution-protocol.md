# Execution Protocol

## Common readiness

1. Resolve repository root, HEAD, branch/detached state, current `git status --short`, `git worktree list --porcelain`, and other worktree dirtiness.
2. Read `AGENTS.md`, the source-of-truth docs, active Slice plan/tasks, the Task record, dependency files, and the complete current diff including untracked paths.
3. Run `inspect_state.py`. It reports `ordered_candidate` separately from `executable_task`; only current-context Task authority plus the fixed baseline gate can make a Task executable.
4. Stop for pre-existing unrelated changes, multiple active Tasks, unmet dependencies/entry gates, an unconfigured policy, or same-Slice activity in another worktree. Never mutate another worktree.
5. Record the implementation base and pre-existing diff before any authorized write.

## `run-next`

Run exactly one uniquely executable Task. Read its Goal, Contract, Acceptance, Verification, Dependencies, Out of Scope, policy, and Human escalation conditions. Mark it `IN_PROGRESS` in its existing record, implement only the bounded change, run targeted checks and `verify_task.py`, run `check_scope.py` and diff/path checks, record real commands and exit codes, and mark `DONE` only when Acceptance and verification pass. Stop before another Task.

## `snapshot`

A snapshot is one local WIP commit for independent review, never acceptance or integration authority.

1. Require `DONE`, passing deterministic gates, exact Task-scoped paths, and no unrelated residue.
2. Refuse a snapshot on `main`, `master`, configured protected refs, or a commit already directly held by a protected ref. A task branch or detached checkout is valid. Policy cannot remove the built-in protections.
3. Stage only exact Task paths, inspect the complete cached diff, create one canonical WIP commit, and do not amend an existing reviewed snapshot.
4. Require clean `HEAD == snapshot_head` and `base_head` as an ancestor of `snapshot_head`.
5. Emit `verify_commit_readiness.py ... --evidence` with canonical Slice/Task, base, snapshot, mode, changed paths, file type/mode, content-bound digest, risk, verification results, and known limits. Hand this immutable input to a separate reviewer.

## `review`

The reviewer uses a separate clean Session/Worktree at the exact `snapshot_head`, recomputes immutable evidence, and inspects only `base_head..snapshot_head` plus source-of-truth Acceptance and actual verification records. Task-review evidence requires the selected Task to be strictly `DONE`; `IN_PROGRESS` fails closed. Any identity, path, mode/type, content, or cleanliness mismatch is a failure. Output only `AI_REVIEW_PASS`, `AI_REVIEW_NEEDS_CHANGES`, or `BLOCKED`; a pass says `AI_REVIEW_PASS — Awaiting explicit Human approval`. Fixes require a new snapshot/digest.

## `checkpoint`

`verify_commit_readiness.py --checkpoint` is a Human-approval handoff, not an acceptance operation. It validates immutable identity/scope/digest and ignores caller `--verification-pass`. Missing, invalid, or mismatched evidence reports `BLOCKED / CHECKPOINT_NOT_READY`. Only complete matching evidence with `AI_REVIEW_PASS` and a sufficient reviewed risk tier may report `HUMAN_APPROVAL_REQUIRED / CHECKPOINT_READY — Awaiting explicit Human approval`. Every Task policy is `human-decision`; no checkpoint is accepted automatically. Integration and push remain false. No transaction-level ref audit or temporary verification artifact is used.

## `slice-review` and `integrate-approved`

After every configured Slice Task is `DONE`, independently review the complete Slice range using the union of all configured Task scopes. The supplied Task must exactly match the policy's explicit `completion_task`; any other Task identity fails closed. Continue to reject core Artifact changes, unauthorized dependencies, forbidden paths, identity mismatches, and aggregate HIGH-risk conditions. Stop for the Human merge/push decision. Integration or a local integration commit requires explicit current-context Human authorization for the exact range and target. Push is a separate explicit authorization and is prohibited by default.
