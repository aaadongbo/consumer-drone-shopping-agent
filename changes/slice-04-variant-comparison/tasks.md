# Slice 4 Ordered Implementation Tasks — Variant 比较

> 状态：IMPLEMENTATION AUTHORIZED / Formal Slice task table
>
> Human 已在当前上下文授权将 S04 planning baseline `5af0296e7a55ad7a08587772929e3f37e2f420a7` 转为正式执行；本表使用 workflow formal Task state（`NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` / `DONE`）。实现仍须按单 Task、scope、verification、review 和 Human escalation gates 执行。

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Comparison set identity and provenance contract | DONE | Slice 3 completion + Slice 4 planning approval + stable Shopify Variant ID mapping |
| T02 | Bounded member validation and resolution | DONE | T01 |
| T03 | Per-member normalized facts and Evidence binding | NOT_STARTED | T02 |
| T04 | Read-only dynamic facts and freshness guard | NOT_STARTED | T02, T03 |
| T05 | Comparison answer / fallback walking skeleton | NOT_STARTED | T03, T04 |
| T06 | Slice 4 verification matrix and completion evidence | NOT_STARTED | T05 |

## T01 — Comparison set identity and provenance contract

- **Goal**：定义 Slice-local `ComparisonSet`、`ComparisonMember`、`MemberProvenance` 与不变的 per-member identity。
- **Why**：比较必须先成为多成员对象，不能把 Slice 3 的 typed handoff 悄悄折叠为单对象，也不能污染 confirmed context。
- **Scope**：未来 `backend/conversation/` internal value objects、contract fixtures、unit / contract tests 和 Execution Record。
- **Contract**：`ComparisonSet`（2..4）、`ComparisonMember`（store/product/variant）、explicit / confirmed-context provenance、correlation id、clarification / fallback reason。
- **Acceptance**：集合中每个 member 都有独立 Store/Product/Variant identity 与来源；comparison 不写 ConversationState；Page Context 不可补全成员；公开 wire schema 改动先停。
- **Verification**：Static + Unit + Contract identity / provenance matrix。
- **Dependencies**：Slice 3 completion + Slice 4 planning approval + authorized stable Shopify Variant ID mapping。
- **Out of Scope**：解析、代选、Catalog / Shopify 读取、比较表、public contract、RAG、推荐。

## T02 — Bounded member validation and resolution

- **Goal**：将 S3 `COMPARISON_SET` handoff 校验为 2–4 个 distinct、same-store、same-Product 的具体 Variant members。
- **Why**：歧义、越界和 ownership mismatch 必须在读取事实前 fail closed，避免错误对象进入比较。
- **Scope**：未来 `backend/conversation/` / `backend/catalog/` resolution adapter、fixtures、unit / integration tests。
- **Contract**：member resolution outcome、same-store / ownership guard、duplicate / count failure、typed clarification / cross-Product deferral。
- **Acceptance**：不默认首项；Product-only、zero/many resolution、foreign-store、重复、1/5 members、Variant ID 未就绪和 ownership mismatch 都明确澄清 / fallback；显式与 confirmed-context provenance 保留；跨 Product 行为遵循已批准的 Slice 4 规划边界。
- **Verification**：Unit resolution matrix + Integration handoff boundary tests。
- **Dependencies**：T01。
- **Out of Scope**：新的 Product auto-selection policy、改变 S3 precedence、dynamic facts、recommendation、RAG。

## T03 — Per-member normalized facts and Evidence binding

- **Goal**：读取并聚合比较所需的静态规范化事实，同时建立 `ComparisonFact` 与 `ComparisonEvidenceBinding` 的 member gate。
- **Why**：比较价值来自可比较事实，但任何跨 Variant 复用 Evidence 都会制造不存在的商品组合。
- **Scope**：未来 `backend/catalog/` / `backend/evidence/` adapters、unit / contract / integration tests。
- **Contract**：field key、normalized value / unit、KNOWN / UNKNOWN / NOT_APPLICABLE、member_id、catalog revision、Evidence locator / scope verdict。
- **Acceptance**：事实与 Evidence 完全绑定所属 member；UNKNOWN、NOT_APPLICABLE 不混淆；不存在输入时不派生结论；错误 member Evidence 注入被拒绝。
- **Verification**：Unit table + Contract binding round-trip + Integration injection guard。
- **Dependencies**：T02。
- **Out of Scope**：动态 price/inventory、文档 RAG、Derived Evidence、ranking、public answer payload。

## T04 — Read-only dynamic facts and freshness guard

- **Goal**：为已验证成员读取当前价格、库存和 availability，并输出 member-scoped freshness / degradation。
- **Why**：动态事实是比较中的高风险差异，不能用旧 catalog、文档或其他成员的 ToolResult 替代。
- **Scope**：未来 `backend/shopify/` read adapter integration、`backend/evidence/` freshness binding、integration / zero-write tests。
- **Contract**：member-scoped dynamic `ComparisonFact`、ToolResult identity、observed_at / freshness verdict、unavailable fallback。
- **Acceptance**：只读 allowlist；每项动态事实匹配 member identity 且披露 freshness；failed / stale / mismatched read 变为 unavailable，不形成事实；write ledger 为零。
- **Verification**：Integration current-commerce fixtures + stale/failure cases + zero-write ledger。
- **Dependencies**：T02, T03。
- **Out of Scope**：真实 credentials、Shopify write、retry/backoff framework、并行读取定案、RAG。

## T05 — Comparison answer / fallback walking skeleton

- **Goal**：打通 typed handoff → validated set → static/dynamic facts → per-member Evidence → internal comparison answer / fallback 的最小闭环。
- **Why**：只有端到端路径才能证明 provenance、事实状态、freshness、trace 与比较展示没有在拼装时失去身份边界。
- **Scope**：未来 `backend/application/` internal flow、`backend/conversation/` / `backend/catalog/` / `backend/evidence/` adapters、contract / integration / e2e tests。
- **Contract**：internal `ComparisonAnswer` 或 typed handoff、rows/differences、per-member bindings、disclosure、fallback、correlation trace。
- **Acceptance**：2–4 同 Product Variant happy path 逐成员披露；无效集、缺证、动态读取失败都可行动降级；confirmed context 不变；不修改 public `AnswerEnvelope` 或 Widget schema。
- **Verification**：Contract + Integration + E2E comparison journeys。
- **Dependencies**：T03, T04。
- **Out of Scope**：正式 Widget、跨 Product、推荐、RAG、Shopify write、外部服务。

## T06 — Slice 4 verification matrix and completion evidence

- **Goal**：覆盖 S4-A01～S4-A11 与 plan 的 11 个矩阵场景，形成可审计 completion evidence。
- **Why**：比较常在边界组合时发生 identity、证据与 freshness 误配；完成前必须在完整闭环证明 fail-closed 行为。
- **Scope**：tests / eval fixtures、Task Execution Record、independent Slice review 输入。
- **Contract**：S4 acceptance matrix、comparison correlation trace、zero-write and freshness evidence。
- **Acceptance**：所有 Acceptance 均有可定位 PASS 证据；full suite、scope/diff、secret、zero-write、identity、Evidence 和 freshness gates 通过。
- **Verification**：Static + Unit + Contract + Integration + E2E + full suite + scope/diff review + independent Slice review。
- **Dependencies**：T05。
- **Out of Scope**：新业务能力、workflow 实现、Slice 5/6、integration、push。

## Workflow risk and verification

所有任务均为 HIGH：它们触及比较 Product Behavior、identity / Evidence safety boundary、Shopify dynamic read 或最终 answer boundary。实施时每项都必须先获得当前上下文 Human decision；不得从 HIGH 自动推进。每个任务要运行 policy-selected targeted verification；T06 额外运行 full suite。公共 Contract、Product Behavior、Architecture、Acceptance、Accepted Decision、external service、Shopify write、dependency 或安全边界变更无论配置如何都必须 Human escalation。

计划中的命令、测试名与通过数量不是执行证据；Execution Record 只能记录实际运行的命令、exit code 与结果。

## Execution Records

### S04-T01 — Comparison set identity and provenance contract

- **Status**：DONE
- **Implementation base**：`833b53fed1b76690f9dc4908306fb1cb768f8cc0`
- **Changed paths**：
  - `backend/conversation/__init__.py`
  - `backend/conversation/comparison.py`
  - `changes/slice-04-variant-comparison/tasks.md`
  - `tests/contract/test_s04_t01_comparison_contract.py`
  - `tests/fixtures/s04_t01_comparison_contract_golden.json`
  - `tests/unit/test_s04_t01_comparison_identity.py`
- **Scope result**：`python .agents/skills/drone-slice-workflow/scripts/check_scope.py S04-T01` exit 0; no disallowed paths, no core artifact changes, no dependency changes.
- **Verification commands**：
  - `uv run --frozen pytest tests/contract/test_s04_t01_comparison_contract.py tests/unit/test_s04_t01_comparison_identity.py -q` exit 0; `8 passed in 0.08s`.
  - `uv run --frozen ruff check backend/conversation/comparison.py backend/conversation/__init__.py tests/contract/test_s04_t01_comparison_contract.py tests/unit/test_s04_t01_comparison_identity.py` exit 0; all checks passed.
  - `uv run --frozen ruff format --check backend/conversation/comparison.py backend/conversation/__init__.py tests/contract/test_s04_t01_comparison_contract.py tests/unit/test_s04_t01_comparison_identity.py` exit 0; `4 files already formatted`.
  - `git diff --check` exit 0.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S04-T01` exit 0; workflow-selected verification complete, including compile, ruff check, ruff format check, targeted pytest, diff/core/dependency gates; targeted pytest result `8 passed in 0.07s`.
- **Result**：Introduced Slice-local internal `ComparisonSet`, concrete Variant `ComparisonMember`, `MemberProvenance`, scope status and fallback reason contracts; added golden matrix with the approved stable Variant ID mapping; preserved public wire schemas and existing S03 handoff behavior.
- **Review / snapshot**：HIGH task under current Human authorization; local immutable WIP snapshot `778e51a` created for scope separation. This is not integration or push authority.

### S04-T02 — Bounded member validation and resolution

- **Status**：DONE
- **Implementation base**：`778e51a`
- **Changed paths**：
  - `backend/conversation/__init__.py`
  - `backend/conversation/comparison.py`
  - `backend/conversation/comparison_resolution.py`
  - `changes/slice-04-variant-comparison/tasks.md`
  - `tests/integration/test_s04_t02_comparison_handoff_boundary.py`
  - `tests/unit/test_s04_t02_comparison_resolution.py`
- **Verification commands**：
  - `uv run pytest -m 'unit or integration' tests/unit/test_s04_t02_comparison_resolution.py tests/integration/test_s04_t02_comparison_handoff_boundary.py -q` exit 0; `10 passed in 0.06s`.
  - `uv run ruff check --fix backend/conversation/comparison.py backend/conversation/comparison_resolution.py backend/conversation/__init__.py tests/unit/test_s04_t02_comparison_resolution.py tests/integration/test_s04_t02_comparison_handoff_boundary.py` exit 0; one mechanical fix applied, then clean.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S04-T02 --pretty` exit 0; workflow-selected verification complete, including compile, ruff check, ruff format check, targeted pytest, diff/core/dependency gates; targeted pytest result `10 passed in 0.08s`.
- **Result**：Materialized S3 `COMPARISON_SET` handoff into a bounded same-store, same-Product concrete Variant `ComparisonSet`; Product-only, Page Context member provenance, foreign-store, ownership mismatch, unresolved Variant and cross-Product requests fail closed with typed clarification/deferral before fact or dynamic reads.
- **Review / snapshot**：HIGH task under current Human authorization; local immutable WIP snapshot will be created before S04-T03 because T03 scope excludes T02 conversation files. This is not integration or push authority.
