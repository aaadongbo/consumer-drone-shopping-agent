# Execution Protocol

## Common readiness

1. Resolve repository root, HEAD, branch/detached state, current `git status --short`, `git worktree list --porcelain`, and other worktree dirtiness.
2. Read `AGENTS.md`, the source-of-truth docs, active Slice plan/tasks, the Task record, dependency files, and the complete current diff including untracked paths.
3. Run `inspect_state.py`. It reports `ordered_candidate` separately from `executable_task`; only current-context Task authority plus the fixed baseline gate can make a Task executable.
4. Stop for pre-existing unrelated changes, multiple active Tasks, unmet dependencies/entry gates, an unconfigured policy, or same-Slice activity in another worktree. Never mutate another worktree.
5. Record the implementation base and pre-existing diff before any authorized write.

## `run-next`

Run the unique ordered candidate without crossing its risk gate. A LOW Task may use one explicit Slice authorization (`inspect_state.py --authorize-slice S02`) and, after its targeted gates, immutable snapshot, and independent `AI_REVIEW_PASS`, may continue to the next ordered LOW Task in the same Slice Implementation Session. MEDIUM requires a Human key-checkpoint after its independent review; HIGH requires the existing per-Task Human gate. Always mark only the current Task `IN_PROGRESS`/`DONE`, keep one Task active at a time, record real commands and exit codes, and stop on any review finding, dependency change, scope mismatch, or risk escalation.

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

`verify_commit_readiness.py --checkpoint` is a routing handoff, never an acceptance operation. It validates immutable identity/scope/digest, runs the policy-selected targeted verification against that exact snapshot (full suite for `slice-review`), and ignores caller `--verification-pass`. Missing, invalid, mismatched, or plan-only verification reports `BLOCKED / CHECKPOINT_NOT_READY`. Complete matching LOW evidence with `AI_REVIEW_PASS` may report `AUTO_ADVANCE_ELIGIBLE`; this only permits the next ordered LOW implementation Task and leaves `checkpoint_accepted`, integration, and push false. A Reviewer-reported tier above policy always routes to the higher Human gate. MEDIUM/HIGH evidence reports `HUMAN_APPROVAL_REQUIRED / CHECKPOINT_READY — Awaiting explicit Human approval`. Every Task still uses `checkpoint_policy: human-decision`; the risk-tier automation field controls only advancement routing.

## `slice-review` and `integrate-approved`

After every configured Slice Task is `DONE`, run the full suite and independently review the complete Slice range using the union of all configured Task scopes. The supplied Task must exactly match the policy's explicit `completion_task`; any other Task identity fails closed. Continue to reject core Artifact changes, unauthorized dependencies, forbidden paths, identity mismatches, and aggregate HIGH-risk conditions. Stop for the Human merge/push decision. Integration or a local integration commit requires explicit current-context Human authorization for the exact range and target. Push is a separate explicit authorization and is prohibited by default.

## Verification and human summary

Each Task runs targeted verification selected by policy. Full-suite verification is reserved for Slice completion, unless a shared Contract, dependency, or cross-Task regression requires an earlier escalation. Human-facing output is a compact digest: Task/Slice, risk and human gate, changed paths, Acceptance result, targeted/full test counts, first failures and fixes, AI verdict, immutable digest, and next action. Do not repeat raw command logs unless a failure or escalation needs them.
