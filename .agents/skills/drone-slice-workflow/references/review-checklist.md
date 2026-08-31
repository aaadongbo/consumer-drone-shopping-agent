# Review Checklist

Review behavior before source shape. Read the Task, plan rows, policy, immutable handoff, and existing verification record; inspect only the exact `base_head..snapshot_head` range.

## Evidence identity

- The independent checkout is clean at `snapshot_head`, with `base_head` an ancestor.
- Canonical Slice/Task, base, snapshot, mode, paths, file types/modes, and contents reproduce the supplied digest.
- No staging, working-tree, extra-path, amended/rebased-snapshot, or different-mode residue is present.
- The snapshot is not directly on a protected ref. `main` and `master` remain protected even when policy omits them.
- Scope and deterministic verification output refer to the same immutable range; caller pass claims are not evidence.
- Task review requires the selected Task to be `DONE`. Slice review requires every Task to be `DONE`, the Task identity to equal the explicit policy `completion_task`, and the complete range to pass the union of configured Task scopes plus core Artifact, dependency, forbidden-path, identity, and aggregate HIGH-risk gates.
- The reviewer did not modify or implement the snapshot and remains independent.

## Required findings

- Acceptance behavior is demonstrably satisfied at its required test level.
- Product/Variant/store identity is exact; no default Variant selection or cross-Variant value mixing occurs.
- Evidence, claims, output scope, freshness, and correlation identity bind to the same resolved object and current ToolResult.
- ERROR, PARTIAL, UNKNOWN, missing, and inconsistent ToolResult paths fail closed without stale substitution.
- Shopify stays read-only with zero-write evidence.
- Public Contract, core Artifact, Product Behavior, Architecture, and Accepted Decision changes are absent or explicitly escalated.
- Dependency changes are policy-allowed, minimal, and Task-local; major/cross-Slice dependencies are HIGH/escalated.
- No later Task/Slice behavior, generated residue, secret, raw header, or sensitive trace data appears.
- The Execution Record contains real commands, failures, corrections, exit codes, evidence, and limitations.
- AI verdict, Human approval, WIP snapshot, checkpoint handoff, integration/merge, and push remain distinct.
- Risk routing is respected: LOW may become `AUTO_ADVANCE_ELIGIBLE` only after targeted gates and independent review; MEDIUM requires a key checkpoint; HIGH requires per-Task Human approval. No route authorizes checkpoint acceptance, integration, merge, or push.

## Verdicts

Use `AI_REVIEW_NEEDS_CHANGES` for any actionable correctness, scope, test, evidence, risk, or record defect; list severity and file/line evidence. Use `BLOCKED` only when evidence is unavailable or a Human boundary prevents a conclusion. Use `AI_REVIEW_PASS` only when no actionable finding remains, and include canonical identity, exact range, mode, digest, reviewed risk tier, verification evidence, residual risk, and the wording `AI_REVIEW_PASS — Awaiting explicit Human approval`. The reviewer must not infer a Human gate from LOW auto-advance eligibility.
