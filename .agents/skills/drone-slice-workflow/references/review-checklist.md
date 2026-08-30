# Review Checklist

Review behavior before source shape. Read the current Task and relevant plan matrix rows, then inspect `git status --short`, staged/unstaged diffs, untracked files, `check_scope.py`, `verify_task.py`, and the Task Execution Record.

## Required findings pass

- Every Acceptance item is demonstrably satisfied at its required test level; tests assert behavior rather than names, source text, or line counts.
- Product/Variant/store identity is exact. No default Variant selection or cross-Variant value mixing occurs.
- Evidence, claim bindings, output scope, and freshness belong to the same resolved object; dynamic facts originate in the current ToolResult.
- Trace events describe the order that actually occurred and share the correct correlation identity.
- ERROR, PARTIAL, UNKNOWN, missing, and inconsistent ToolResult paths fail closed without stale/fixture substitution.
- Shopify remains read-only, with no write surface and the required zero-write evidence.
- Public Contract and core Artifact diffs are absent unless explicitly reconciled and authorized.
- Any dependency diff is allowed by the active Slice/Task policy and manually confirmed as minimal and directly required; major or cross-Slice dependencies have been escalated rather than accepted by path alone.
- Review evidence is bound to the normalized current Task ID as well as HEAD and content; evidence from another Task is rejected, and no different Task is `IN_PROGRESS`.
- No later Task or Slice behavior, dependency, generated residue, unchecked untracked file, secret, raw header, or sensitive trace data appears.
- The Execution Record includes real commands, failures, corrections, exit codes, evidence locations, and limitations, consistent with Git and observed results.
- AI and Human authority semantics remain separate.

## Verdicts

Use `AI_REVIEW_NEEDS_CHANGES` when an actionable correctness, scope, test, evidence, or record defect exists. List findings by severity with file/line evidence, then note residual risk.

Use `BLOCKED` only when review cannot reach a conclusion because required evidence is unavailable or a Human authority boundary is reached.

Use `AI_REVIEW_PASS — Awaiting explicit Human approval` only when no actionable finding remains. Include the exact normalized Task ID, reviewed base HEAD, diff SHA-256, and concise verification evidence. Never output `Human Approved` or `APPROVED FOR COMMIT`.
