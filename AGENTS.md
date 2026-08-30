# Project Working Rules

- Treat `docs/`, the active Slice `plan.md`, and its `tasks.md` as the sources of truth. Git, the current diff, those artifacts, and each Task Execution Record jointly express workflow state; do not create a third status file.
- Work on one explicitly authorized Task at a time. Check Git, worktrees, Task state, and dependencies before starting, and never continue automatically into the next Task.
- Protect user changes and every other Session/worktree. Do not overwrite, stage, commit, move, or mix unrelated work, and do not implement another Task or Slice opportunistically.
- Do not independently change Product Behavior, Architecture boundaries, public Contracts, Accepted Decisions, or Acceptance criteria. Reconcile conflicts and stop at the applicable human authority boundary.
- AI review may report only `AI_REVIEW_PASS` or `AI_REVIEW_NEEDS_CHANGES` (or `BLOCKED` when genuinely blocked). AI must not claim `Human Approved` or `APPROVED FOR COMMIT`.
- Commit only after explicit authorization in the current user context. Commit authorization never authorizes push; push is prohibited by default.
- Record only tests and commands actually run, with their real exit codes and results.
