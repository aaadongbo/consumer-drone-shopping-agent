# Reconciliation Rules

Reconciliation is read-only unless the user separately authorizes the identified Artifact changes.

## Report shape

1. **Discovery** — the observed mismatch, with code/test/Git evidence.
2. **Impact** — affected behavior, Task, matrix rows, Contracts, modules, and downstream Tasks.
3. **Classification** — Implementation, Task record, Slice plan, Architecture, Product Spec, or Decision.
4. **Options** — bounded alternatives and tradeoffs.
5. **Recommendation** — the smallest source-of-truth correction supported by evidence.
6. **Authority boundary** — whether the change crosses Human authority and which exact files/semantics need approval.
7. **Blocked work** — what must stop pending a decision.

## Classification rules

- Implementation-only defects are corrected in the current authorized Task and verified against unchanged Acceptance.
- Incorrect or incomplete execution evidence may update only the current Task Execution Record, preserving historical failures and corrections.
- Slice ordering, assumptions, local verification, or Task scope changes require explicit authorization to update plan/tasks.
- Product Behavior, V1 Scope, Acceptance, or quality gates belong to `PROJECT_SPEC.md` and require Human decision.
- Module responsibilities, Architecture boundaries, or core cross-module Contract semantics belong to `ARCHITECTURE.md` and require Human decision.
- Major technical choices or changes to an Accepted Decision belong to `DECISIONS.md`; preserve superseded history.

Never relax an assertion or rewrite Acceptance merely to fit an implementation. Do not update multiple source artifacts “for consistency” before the user approves the classified change. After authorization, modify only the necessary artifacts, re-run affected gates, and return to the current Task; do not enter the next Task.
