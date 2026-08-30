# Execution Protocol

## Common readiness

1. Resolve the repository root, HEAD, branch/detached state, current worktree, `git status --short`, `git worktree list --porcelain`, and other worktree dirtiness.
2. Read repository `AGENTS.md`, the long-lived source artifacts, active Slice plan/tasks, current Task, recent history, dependency files, and the complete current diff including untracked paths.
3. Run `inspect_state.py`. Stop if the current checkout has pre-existing unrelated changes, multiple Tasks are `IN_PROGRESS`, the requested Task is illegal, or dependencies are unmet. Do not mutate another worktree.
4. Establish the starting commit and pre-existing diff before an authorized write.

## `status`

Remain read-only. Present T01–T09 (or every parsed Task) with the formal status, dependencies, dependency satisfaction, active Task, unique next legal Task, all worktrees, dirty paths, and blocking reasons. A dirty other worktree is context, not permission to inspect or modify its implementation.

## `run-next`

Invocation as `$drone-slice-workflow run-next` authorizes implementation of the one unique legal next Task, not a commit or later Task. If the user merely says “继续”, run `status` and request explicit Task execution authority.

1. Select only the unique `NOT_STARTED` Task whose dependencies are all `DONE`.
2. Read that Task’s Goal, Contract, Acceptance, Verification, Dependencies, Out of Scope, plus relevant plan matrix rows and Human Escalation conditions.
3. Change its formal status to `IN_PROGRESS` and record the real start commit/pre-existing diff.
4. Implement the smallest bounded change satisfying the Task. Do not change a public Contract, core Artifact, Acceptance, dependency, or another Task unless separately authorized through reconciliation.
5. Run targeted validation while iterating. Then run `verify_task.py <Task>` and any Task-specific/full gates it does not cover.
6. Run `check_scope.py <Task>`, `git diff --check`, inspect `git status --short`, all untracked files, and the complete diff. Confirm no later Task/Slice behavior, Shopify write surface, or unrelated refactor entered the change. If `dependency_review.changed_paths` is non-empty, manually prove each dependency is minimal, directly required by the approved Task/plan, and not a major or cross-Slice dependency; otherwise stop for Human escalation.
7. Fill the Task Execution Record with actual commands, exit codes, results/evidence, corrections, discoveries, and limitations. Never erase prior failures or fabricate a result.
8. Mark `DONE` only after every Acceptance and Verification item passes. Otherwise remain `IN_PROGRESS` or use `BLOCKED` only under the project’s blocker rules.
9. Perform `review` using the checklist. Stop after the verdict and await Human response. Never commit or enter the next Task automatically.

## `review`

Review the entire `git diff HEAD`, staged/unstaged changes, and untracked files independently of implementation intent. Verify the Execution Record against actual evidence. Output one leading verdict only:

- `AI_REVIEW_PASS — Awaiting explicit Human approval`
- `AI_REVIEW_NEEDS_CHANGES`
- `BLOCKED`

On pass, run `verify_commit_readiness.py <Task> --hash-only` and report `task`, `base_head`, and its digest. The digest domain includes the normalized Task ID and HEAD OID plus tracked and untracked changed paths and their working-tree content; staging alone does not change it. Snapshot creation fails if another Task is active or scope does not belong to the requested Task. This snapshot is workflow evidence, not Human approval.

## `commit-approved`

“继续”, historical approval text, a `DONE` status, or an old Execution Record does not authorize commit. The current user context must explicitly approve the current Task’s local commit.

1. Confirm the Task is `DONE`, no different Task is `IN_PROGRESS`, the last review verdict is `AI_REVIEW_PASS`, and the reviewed Task ID, HEAD, and diff hash still describe the complete current change.
2. Re-run the necessary verification and scope gates. If any result differs, stop and return to review.
3. Resolve the exact current-Task paths from the reviewed diff; reject unrelated or untracked extras. Stage those exact paths only. Never use a broad stage command when unrelated paths exist.
4. Run `verify_commit_readiness.py <Task> --reviewed-head <oid> --reviewed-diff-sha256 <sha256> --ai-review-pass --human-approved` after staging. If and only if `dependency_review.manual_confirmation_required` is true, manually verify the dependency condition and add `--dependency-review-confirmed`; without it the gate must return `DEPENDENCY_MANUAL_CONFIRMATION_REQUIRED`. The approval flags may be supplied only from the corresponding current workflow evidence and user authority.
5. Require the same Task and HEAD, no different active Task, any required dependency confirmation, no unstaged Task residue, no extra staged path, a passing cached diff check, unchanged reviewed hash, and `COMMIT_READY`.
6. Inspect `git diff --cached --stat` and the complete `git diff --cached`. Commit once using the project’s existing message convention.
7. Verify HEAD, commit contents, and worktree status. Report the local commit and any remaining files. Do not push and do not start the next Task.

## Failure handling

Preserve nonzero exit codes and their summaries. Diagnose within Task scope, correct bounded implementation errors, and rerun the affected command. Reconciliation or Human escalation is required when correction would change Product Behavior, Architecture boundaries, a public Contract, Accepted Decision, Acceptance, dependencies, or another Task/Slice.

An active Slice or Task absent from `references/task-scope-policy.json` fails closed. Derive a new policy entry only from an approved plan/tasks Artifact, show its allowed paths, dependency mode, and verification selection for Human review, and update the policy only with explicit authorization. Never reuse another Slice's Task ID policy by position.
