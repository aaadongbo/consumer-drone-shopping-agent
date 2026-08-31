# Slice 2 Ordered Implementation Tasks

> 状态：APPROVED / Implementation gated by Workflow Simplification
> 执行设计：[plan.md](./plan.md)
> 本文件定义的目标、Scope、Acceptance 和 T01～T07 已获 Human Final Approval；具体实现授权以当前 Human 上下文和 Execution Record 为准。

## 1. Naming and Status

Slice 2 的文件路径已经包含 `slice-02`；任务在本文件内使用 `T01`～`T07`，完整引用使用 `S02-T01`～`S02-T07`。这样既兼容仓库现有 workflow 的局部 Task ID，又不会与 Slice 1 的 T01～T09 混淆。

任务状态仅使用：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`DONE`。

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | S02 数据/目录最小映射 | DONE | Slice 1 closed; Slice 2 plan approved; Workflow Simplification baseline |
| T02 | S02 单轮 ConstraintPatch 与规范化 | DONE | T01 |
| T03 | S02 Variant-level HARD eligibility | DONE | T02 |
| T04 | S02 SOFT preference baseline | DONE | T03 |
| T05 | S02 Product-grouped recommendation contract | DONE | T03, T04 |
| T06 | S02 单轮推荐 Walking Skeleton | DONE | T05 |
| T07 | S02 Verification Matrix 与 Completion Evidence | NOT_STARTED | T06 |

S02-T01、S02-T02、S02-T03、S02-T04、S02-T05 已完成、reviewed 并集成到 `main`。当前 Human 上下文已授权并完成 S02-T06；S02-T07 未获实现授权，不得因为 T06 已完成而自动执行下一 Task。

## 2. Task Details

### T01 — S02 数据/目录最小映射

- **Goal**：为单轮推荐建立最小匿名 Product/Variant + commerce fixture。
- **Why**：eligibility 只能在身份完整、字段状态明确的 Variant 上验证。
- **Scope**：`backend/catalog/`、受控 fixture、S02 unit/data validation tests；必要时只纳入 S02 数据 staging 的最小派生记录。
- **Contract**：`ProductRecord`、`VariantRecord`、`AttributeValue`、`ToolResult`、`store_id → product_id → variant_id`。
- **Acceptance**：字段、单位、UNKNOWN/NOT_APPLICABLE、可售快照、observed_at 和证据来源可验证；没有真实客户/订单/凭据。
- **Verification**：Static + Unit + Data validation。
- **Dependencies**：Slice 1 closed + Slice 2 Human Final Approval + approved Workflow Simplification baseline + Slice 2 Task Policy。
- **Out of Scope**：真实 Shopify API、训练数据、文档 RAG、多轮 State、全量数据导入。

### T02 — S02 单轮 ConstraintPatch 与规范化

- **Goal**：将有限单轮输入转换为可比较的规范化约束。
- **Why**：后续资格判断不能直接消费自然语言或隐含单位。
- **Scope**：`backend/conversation/` 或局部 constraint module、deterministic parser、contract/unit tests。
- **Contract**：single-turn `ConstraintPatch`、`NormalizedConstraint`；复用 `TurnRequest`。
- **Acceptance**：支持已批准字段的 ADD/UPDATE/NO_CHANGE、单位和 HARD/SOFT；无效/不支持输入安全降级；不产生多轮 state。
- **Verification**：Contract + Unit。
- **Dependencies**：T01。
- **Out of Scope**：LLM、撤回/跳过/冲突合并、revision、持久化。

### T03 — S02 Variant-level HARD eligibility

- **Goal**：对每个 Variant 做确定性硬约束和可售性判断。
- **Why**：正式推荐的硬正确性必须可审计且不能交给模型。
- **Scope**：`backend/catalog/` eligibility evaluator、rejection reasons、table-driven tests。
- **Contract**：`NormalizedConstraint` → `EligibilityResult`。
- **Acceptance**：UNKNOWN/missing 不通过；动态可售状态来自当前 snapshot；不跨 Variant 混合；保留身份和拒绝原因。
- **Verification**：Unit + Integration。
- **Dependencies**：T02。
- **Out of Scope**：SOFT 排序、推荐文案、RAG、学习模型。

### T04 — S02 SOFT preference baseline

- **Goal**：生成透明、稳定、可替换的软偏好匹配信号。
- **Why**：Slice 2 需要表达偏好取舍，但不能让软偏好覆盖硬资格。
- **Scope**：局部 ranking signal module、tie-break 和 unit tests。
- **Contract**：eligible `VariantRecord` + active SOFT constraints → deterministic signals/order。
- **Acceptance**：排序稳定、理由可解释、硬不满足永不晋级；权重不是长期 Decision。
- **Verification**：Unit + deterministic replay。
- **Dependencies**：T03。
- **Out of Scope**：learning-to-rank、利润/库存目标、外部行为数据。

### T05 — S02 Product-grouped recommendation contract

- **Goal**：定义最小候选、Product 分组、理由与 Evidence binding。
- **Why**：用户看到 Product，但资格和事实必须保留真实 Variant。
- **Scope**：`backend/evidence/`、响应 contract、contract tests。
- **Contract**：`RecommendationCandidate`、候选列表、既有 `AnswerEnvelope` identity/fallback/trace 语义。
- **Acceptance**：最多三款不同 Product；Variant 明确；Evidence/claim scope 一致；若需公共 schema 核心变更则停止升级。
- **Verification**：Contract + Unit。
- **Dependencies**：T03、T04。
- **Out of Scope**：正式 Widget、比较表、RAG citations、多轮状态。

### T06 — S02 单轮推荐 Walking Skeleton

- **Goal**：打通一轮推荐的 deterministic E2E 闭环。
- **Why**：验证从输入到候选、理由、证据和 fallback 的真实协作关系。
- **Scope**：`backend/api/`、`backend/agent/`、`backend/catalog/`、`backend/evidence/` 既有边界及 integration/e2e tests。
- **Contract**：`TurnRequest`、ConstraintPatch、EligibilityResult、RecommendationCandidate、AnswerEnvelope、Trace。
- **Acceptance**：happy path、无匹配、UNKNOWN、不可售、跨商店和工具失败均 fail closed；zero Shopify writes。
- **Verification**：Integration + E2E + scope/static。
- **Dependencies**：T05。
- **Out of Scope**：MongoDB/Redis、真实 Shopify/model、SSE、Widget、Slice 3～7。

### T07 — S02 Verification Matrix 与 Completion Evidence

- **Goal**：补齐 S02 Acceptance 的可回放矩阵并记录实际验证证据。
- **Why**：只有完整证据才能判断单轮推荐是否可关闭。
- **Scope**：`tests/`、`eval/datasets/` 的最小候选/说明、`tasks.md` Execution Record。
- **Contract**：本 plan 的 S2-A01～S2-A13 及公共 response/trace 语义。
- **Acceptance**：矩阵全部 PASS；full suite、scope、zero-write、identity/evidence checks 通过；不把真实 smoke 或训练当作必需。
- **Verification**：Static + Unit + Contract + Integration + E2E + diff review。
- **Dependencies**：T06。
- **Out of Scope**：Slice 3、多轮 State、RAG、比较、正式 Widget、模型微调、push。

## 3. Execution Record

### T01 — S02 数据/目录最小映射

- **Status**：`DONE`
- **Start commit**：`d23c988e6c523e879c718c51474ae13d348d5c14`
- **Start state**：当前 detached worktree 无 tracked/untracked/staged 修改；`main` 与当前 HEAD 均指向 workflow simplification baseline。
- **Authority/readiness**：当前 Human 上下文仅授权 `S02-T01`；`inspect_state.py --authorize-task S02-T01` 报告唯一 `executable_task` 为 `S02-T01`，Slice 1 closed、Slice 2 Planning approved、implementation gate satisfied。
- **Other worktrees**：`/Users/russeell/.codex/worktrees/6408/消费级无人机智能导购Agent` 存在与本 Task 无关的 workflow dirty paths；无 active Task，本轮只报告与隔离，不修改该 worktree。
- **Initial verification**：`uv lock --check` exit 0；`uv run ruff check .` exit 0；`uv run ruff format --check .` exit 0；`uv run pytest -q` exit 0（207 passed）。
- **Implementation**：新增 store-scoped 匿名 synthetic catalog/commerce fixture，直接复用 `ProductRecord`、`VariantRecord`、`AttributeValue` 和 `ToolResult`；静态目录与动态价格/库存/可售性分层，支持可注入 `observed_at`、稳定排序、明确单位、完整 store/product/variant 归属和加载时数据校验。主商店样本包含 3 Product / 4 Variant，覆盖可推荐、不可售、UNKNOWN HARD 字段、`NOT_APPLICABLE`、不同 Product 分组和跨 Variant 差异；隔离商店使用同 product/variant ID 但不同数值，用于暴露遗漏 `store_id` 的混用。
- **Changed paths**：`backend/catalog/__init__.py`；`backend/catalog/fixture.py`；`tests/unit/test_s02_t01_catalog_fixture.py`；`changes/slice-02-single-turn-recommendation/tasks.md`。无 staged paths。
- **Targeted/import verification**：`uv run python -c 'from backend.catalog ...'` exit 0；`uv run pytest tests/unit/test_s02_t01_catalog_fixture.py -q` exit 0（10 passed）。
- **Final static/lock verification**：`uv lock --check` exit 0；`uv run ruff check .` exit 0；`uv run ruff format --check .` exit 0；`git diff --check` exit 0。
- **Final test verification**：`uv run pytest -m unit -q` exit 0（69 passed, 148 deselected）；`uv run pytest -m contract -q` exit 0（110 passed, 107 deselected）；`uv run pytest -q` exit 0（217 passed）。
- **Workflow verification**：`python .agents/skills/drone-slice-workflow/scripts/check_scope.py S02-T01` exit 0（`ok: true`，LOW，无 disallowed/core/dependency/forbidden path）；`python .agents/skills/drone-slice-workflow/scripts/verify_task.py S02-T01` exit 0（`ok: true`）。
- **Post-completion state inspection**：`python .agents/skills/drone-slice-workflow/scripts/inspect_state.py` exit 1（`ok: false`），唯一 blocker 为未 commit 的 Task 完成产物导致的预期 `CURRENT_WORKTREE_DIRTY`；同一输出确认 T01=`DONE`、T02=`NOT_STARTED`、`executable_task=null`，未执行下一 Task。
- **Artifact/dependency/diff review**：`git diff --quiet HEAD -- docs/PROJECT_SPEC.md docs/ARCHITECTURE.md docs/REFERENCE_ANALYSIS.md docs/DECISIONS.md` exit 0；`git diff --quiet HEAD -- pyproject.toml uv.lock` exit 0；complete changed-path/untracked/staged review 和 `git status --short --untracked-files=all` exit 0，只包含上述四个 Task-scoped paths。
- **First failure and fix**：首次 `uv run ruff check backend/catalog tests/unit/test_s02_t01_catalog_fixture.py` exit 1（3 处 E501），首次 targeted `ruff format --check` exit 1（2 个新文件需格式化）；执行 `uv run ruff format backend/catalog tests/unit/test_s02_t01_catalog_fixture.py` 后，同范围 lint/format/targeted tests 全部 exit 0。未隐藏首次失败。
- **Limitations**：仅为受控 synthetic fixture/data validation baseline；未连接真实 Shopify，未创建训练数据，未实现 ConstraintPatch、eligibility、ranking、recommendation response、API 或 E2E。未 commit、未 push，也未创建 snapshot/checkpoint。
- **Recommended Next Task**：先完成 `S02-T01` independent AI Review / snapshot / checkpoint，经 Human 决策后才进入 `S02-T02`。

### T02 — S02 单轮 ConstraintPatch 与规范化

- **Status**：`DONE`
- **Start commit**：`736161c39dee9aeb7c1a12f14101a7ab82c3d6d6`
- **Start state**：`main` 工作区干净；`inspect_state.py --authorize-task S02-T02` 报告唯一 `executable_task` 为 `S02-T02`；T01=`DONE`，T02=`NOT_STARTED`，T03=`NOT_STARTED`。
- **Authority/readiness**：当前 Human 上下文明确授权 `S02-T02`，不授权 `S02-T03`；workflow policy 报告 T02 risk=`MEDIUM`、human gate=`key-checkpoint`、verification=`targeted`。
- **Implementation**：新增 conversation-local `ConstraintPatch`、`NormalizedConstraint`、deterministic parser 和 normalization helpers；覆盖预算上限、起飞重量上限、最低电池数、用途偏好、相机分辨率偏好和避障偏好。HARD/ SOFT 分类保持透明，unsupported input 返回 `NO_CHANGE`，不创建多轮 state、revision、持久化或 LLM 调用。
- **Changed paths**：`backend/conversation/__init__.py`；`backend/conversation/constraints.py`；`tests/contract/test_s02_t02_constraints_contract.py`；`tests/unit/test_s02_t02_constraints.py`；`changes/slice-02-single-turn-recommendation/tasks.md`。
- **First failure and fix**：首次 targeted collection exit 2，原因是 `WireModel` 未从 `backend.common` re-export；改为从 `backend.common.contracts` 局部导入。首次 Ruff exit 1，包含 forward-ref 引号、import 排序和一处长行；执行 Ruff fix/format 并手动折行后通过。
- **AI Review finding and fix**：独立 review 首轮返回 `AI_REVIEW_NEEDS_CHANGES`，指出非法预算币种会被静默当作 CNY、非数值字段接受无效 operator、数值字段接受 bool。已新增回归并修正：`USD/美元` 预算输入返回 `NO_CHANGE`，field/operator compatibility fail closed，numeric fields reject bool。
- **Targeted verification**：`uv run pytest tests/unit/test_s02_t02_constraints.py tests/contract/test_s02_t02_constraints_contract.py -q` exit 0（28 passed after review fix）。
- **Workflow verification**：`python .agents/skills/drone-slice-workflow/scripts/check_scope.py S02-T02 --repo .` exit 0（`ok: true`，MEDIUM，无 disallowed/core/dependency/forbidden path）；`python .agents/skills/drone-slice-workflow/scripts/verify_task.py S02-T02 --repo .` exit 0（`ok: true`，203 passed, 38 deselected）。
- **Layered tests**：`uv run pytest -m unit -q` exit 0（81 passed, 160 deselected）；`uv run pytest -m contract -q` exit 0（122 passed, 119 deselected）；`uv run pytest -q` exit 0（241 passed）。
- **Static/lock/diff verification**：`uv run ruff check .` exit 0；`uv run ruff format --check .` exit 0；`uv lock --check` exit 0；`git diff --check` exit 0；core Artifact and dependency zero-diff checks passed through `verify_task.py`.
- **Limitations**：仅实现 single-turn deterministic parsing and normalization；未实现 T03 eligibility、T04 SOFT ranking、T05 recommendation contract、T06 walking skeleton、真实 Shopify/model、持久化 state 或公共 AnswerEnvelope 扩展。
- **Recommended Next Task**：先完成 `S02-T02` snapshot、independent AI Review 和 MEDIUM key-checkpoint；经 Human 决策后才可进入 `S02-T03`。

### T03 — S02 Variant-level HARD eligibility

- **Status**：`DONE`
- **Start commit**：`d72a038ca7d7cc3e05145feea5b46147faa84e6e`
- **Start state**：从干净 `main` 创建任务分支 `codex/s02-t03-snapshot`；`inspect_state.py --authorize-task S02-T03` 报告唯一 `executable_task` 为 `S02-T03`；T01、T02=`DONE`，T03=`NOT_STARTED`，T04=`NOT_STARTED`。
- **Authority/readiness**：当前 Human 上下文明确批准集成 `S02-T02` snapshot `a696cc1fd8ed024b2f9b7abb6c08224828629a2c` 到 `main`，并授权执行 `S02-T03`；不授权 `S02-T04`，不授权 push。
- **Implementation**：新增 deterministic `EligibilityResult`、`EvaluatedConstraint` 和结构化 rejection reason；按具体 Variant 结合当前 commerce snapshot 判断 HARD 约束与可售性。`price` 来自当前 commerce，`battery_count`、`takeoff_weight`、`obstacle_sensing` 来自同一 Variant 属性；SOFT 约束在 T03 中被忽略，不参与排序；identity mismatch 直接 fail closed；结果保留 store/product/variant identity 和 commerce `observed_at`。
- **Changed paths**：`backend/catalog/__init__.py`；`backend/catalog/eligibility.py`；`tests/unit/test_s02_t03_eligibility.py`；`tests/integration/test_s02_t03_eligibility_matrix.py`；`changes/slice-02-single-turn-recommendation/tasks.md`。
- **First failure and fix**：首次 targeted pytest exit 2，原因是 unit/integration 测试文件同名导致 pytest import mismatch；将 integration 测试重命名为 `test_s02_t03_eligibility_matrix.py`。首次 Ruff exit 1，包含 unused import、`Iterable` 导入位置和长行；首次 format check exit 1；执行最小导入修正与 `ruff format` 后通过。
- **AI Review finding and fix**：独立 review 首轮返回 `AI_REVIEW_NEEDS_CHANGES`，指出 `ToolResult.PARTIAL` 可能被当作完整 commerce 数据使用，`ToolResult.ERROR` 会抛出异常而不是返回 fail-closed eligibility。已新增回归并修正：非 `SUCCESS` commerce result 统一返回结构化 fail-closed `EligibilityResult`，不使用不完整数据。
- **Targeted verification**：`uv run pytest tests/unit/test_s02_t03_eligibility.py tests/integration/test_s02_t03_eligibility_matrix.py -q` exit 0（12 passed after review fix）。
- **Layered verification**：`uv run pytest -m unit -q` exit 0（92 passed, 165 deselected）；`uv run pytest -m integration -q` exit 0（21 passed, 236 deselected）；`uv run pytest -m contract -q` exit 0（124 passed, 133 deselected）。
- **Workflow verification**：`python .agents/skills/drone-slice-workflow/scripts/check_scope.py S02-T03 --repo .` exit 0（`ok: true`，MEDIUM，无 disallowed/core/dependency/forbidden path）；`python .agents/skills/drone-slice-workflow/scripts/verify_task.py S02-T03 --repo .` exit 0（`ok: true`，policy-selected `unit or integration`：113 passed, 144 deselected）。
- **Full suite**：`uv run pytest -q` exit 0（257 passed after review fix）。
- **Acceptance coverage**：可售且满足所有 HARD 条件的 Variant eligible；不可售、UNKNOWN、NOT_APPLICABLE、missing、PARTIAL/ERROR commerce result、不满足 HARD、跨 Variant/Store commerce identity mismatch 均 fail closed；SOFT 不影响 T03 资格；overlapping ID 的隔离商店不混用主商店数据；`observed_at` 原样传播。
- **Limitations**：未实现 T04 SOFT ranking、T05 Product-grouped recommendation contract、T06 walking skeleton、fallback/response 文案、真实 Shopify/model、RAG、多轮状态、API 或新的依赖。
- **Recommended Next Task**：先完成 `S02-T03` snapshot、independent AI Review 和 MEDIUM key-checkpoint；经 Human 决策后才可进入 `S02-T04`。

### T04 — S02 SOFT preference baseline

- **Status**：`DONE`
- **Start commit**：`789c90aaa19a3f4d811949cbcf7adf756ee6d227`
- **Start state**：`main` 工作区干净；S02-T03 已按 Human approval 集成到 `main`；从 `main` 创建任务分支 `codex/s02-t04-snapshot`；`inspect_state.py --authorize-task S02-T04` 报告唯一 `executable_task` 为 `S02-T04`。
- **Authority/readiness**：当前 Human 上下文明确授权执行 `S02-T04`，不授权 `S02-T05`，不授权 push；workflow policy 报告 T04 risk=`MEDIUM`、human gate=`key-checkpoint`、verification=`targeted`。
- **Implementation**：新增 deterministic `SoftPreferenceSignal` 与 `SoftPreferenceScore`，只对 T03 已判定 `eligible=True` 的 Variant 生成 SOFT 匹配信号并稳定排序；Product-shared `use_case`、`camera_resolution` 与 Variant-specific `obstacle_sensing` 均保留 actual fact；UNKNOWN/NOT_APPLICABLE/missing 仅作为 non-match，不改变 HARD eligibility；tie-break 使用稳定 identity key。
- **Changed paths**：`backend/catalog/__init__.py`；`backend/catalog/preferences.py`；`tests/unit/test_s02_t04_preferences.py`；`changes/slice-02-single-turn-recommendation/tasks.md`。
- **First failure and fix**：首次 targeted pytest exit 1，2 个测试预期错误：`drone-survey` 不是 travel 用途，只匹配 4K；全局 order 不应被断言为纯 tie-break order，因为匹配数优先。已修正测试预期。首次 Ruff exit 1，包含测试长行；`ruff format` 后通过。
- **Targeted verification**：`uv run pytest tests/unit/test_s02_t04_preferences.py -q` exit 0（6 passed）。
- **Policy verification**：`python .agents/skills/drone-slice-workflow/scripts/check_scope.py S02-T04 --repo .` exit 0（`ok: true`，MEDIUM，无 disallowed/core/dependency/forbidden path）；`python .agents/skills/drone-slice-workflow/scripts/verify_task.py S02-T04 --repo .` exit 0（`ok: true`，policy-selected unit：98 passed, 165 deselected）。
- **Static/lock/full verification**：`uv lock --check` exit 0；`uv run ruff check .` exit 0；`uv run ruff format --check .` exit 0；`git diff --check` exit 0；`uv run pytest -q` exit 0（263 passed）。
- **Acceptance coverage**：SOFT 信号透明可审计；排序稳定可复现；HARD 不满足的 Variant 不进入 ranking；UNKNOWN/NOT_APPLICABLE SOFT 字段不会 fail closed 或晋级；identity mismatch 在 scoring 前拒绝；未引入学习排序、长期权重、推荐文案或 Product-grouped response。
- **Limitations**：未实现 T05 Product-grouped recommendation contract、Evidence binding、候选上限、response payload、T06 walking skeleton、真实 Shopify/model、RAG、多轮状态、API 或新依赖。
- **Recommended Next Task**：先完成 `S02-T04` snapshot、independent AI Review 和 MEDIUM key-checkpoint；经 Human 决策后才可进入 `S02-T05`。

### T05 — S02 Product-grouped recommendation contract

- **Status**：`DONE`
- **Start commit**：`639a362458263fed5f98e02ec709464c9a576f20`
- **Start state**：`main` 工作区干净；S02-T04 已按 Human approval 集成到 `main`；从 `main` 创建任务分支 `codex/s02-t05-snapshot`；`inspect_state.py --authorize-task S02-T05` 报告唯一 `executable_task` 为 `S02-T05`。
- **Authority/readiness**：当前 Human 上下文明确授权执行 `S02-T05`，不授权 `S02-T06`，不授权 push；workflow policy 报告 T05 risk=`HIGH`、human gate=`task`、verification=`targeted`。
- **Implementation**：新增 Slice-local `RecommendationCandidateSet`、`RecommendationCandidate` 与 `RecommendationReason`；候选按 Product 分组，最多三款不同 Product，且每个候选保留实际 Variant identity、ProductCard scope、T03 eligibility、T04 soft score、关键事实 Evidence 与 ClaimEvidenceBinding。模型自身验证 ProductCard、Eligibility、SoftScore、Evidence、Claim binding 均与候选 store/product/variant identity 一致；不修改公共 `AnswerEnvelope` 核心语义。
- **Changed paths**：`backend/evidence/__init__.py`；`backend/evidence/recommendation.py`；`tests/unit/test_s02_t05_recommendation_candidates.py`；`tests/contract/test_s02_t05_recommendation_contract.py`；`changes/slice-02-single-turn-recommendation/tasks.md`。
- **First failure and fix**：首次 targeted tests exit 0（8 passed），但首次 Ruff exit 1，包含三处长行；执行 `ruff format` 后仍有一个过长测试函数名，改短后通过。随后为避免仅依赖 builder 约束，补充模型级 invariant 和 3 个 contract regression，targeted 变为 11 passed。
- **AI Review finding and fix**：独立 review 首轮返回 `AI_REVIEW_NEEDS_CHANGES`，指出重复 eligibility identity 可由后值覆盖前值，配合伪造 soft score 将 ineligible Variant 晋级。已新增回归并修正：重复 eligibility identity 一律 fail closed，不允许 shadow/overwrite。
- **Targeted verification**：`uv run pytest tests/unit/test_s02_t05_recommendation_candidates.py tests/contract/test_s02_t05_recommendation_contract.py -q` exit 0（12 passed after review fix）。
- **Policy verification**：`python .agents/skills/drone-slice-workflow/scripts/check_scope.py S02-T05 --repo .` exit 0（`ok: true`，HIGH，无 disallowed/core/dependency/forbidden path）；`python .agents/skills/drone-slice-workflow/scripts/verify_task.py S02-T05 --repo .` exit 0（`ok: true`，policy-selected unit or contract：234 passed, 41 deselected）。
- **Static/lock/full verification**：`uv lock --check` exit 0；`uv run ruff check .` exit 0；`uv run ruff format --check .` exit 0；`git diff --check` exit 0；`uv run pytest -m unit -q` exit 0（103 passed, 171 deselected）；`uv run pytest -m contract -q` exit 0（130 passed, 144 deselected）；`uv run pytest -q` exit 0（275 passed after review fix）。
- **Acceptance coverage**：候选最多三款不同 Product；同 Product 重复 score 不重复占位；ProductCard/Eligibility/SoftScore/Evidence/Claim binding scope 均一致；ineligible Variant 不能晋级；重复 eligibility identity 不能覆盖原始不合格结果；候选暴露实际 Variant；recommendation contract 可 wire JSON round-trip；未新增公共 AnswerEnvelope 字段。
- **Limitations**：未实现 T06 walking skeleton、API 响应组装、推荐自然语言文案、fallback orchestration、真实 Shopify/model、RAG、多轮状态、正式 Widget 或新依赖。
- **Recommended Next Task**：先完成 `S02-T05` snapshot、independent AI Review 和 HIGH task checkpoint；经 Human 决策后才可进入 `S02-T06`。

### T06 — S02 单轮推荐 Walking Skeleton

- **Status**：`DONE`
- **Start commit**：`86ee34106526d8f0c2f21f6df271e9ce4769e079`
- **Start state**：`main` 已按 Human approval fast-forward 集成 S02-T05 snapshot；从干净 `main` 创建任务分支 `codex/s02-t06-snapshot`；`inspect_state.py --authorize-task S02-T06` 报告唯一 `executable_task` 为 `S02-T06`；T01～T05=`DONE`，T06=`NOT_STARTED`，T07=`NOT_STARTED`。
- **Authority/readiness**：当前 Human 上下文明确批准集成 `S02-T05` snapshot `86ee34106526d8f0c2f21f6df271e9ce4769e079` 到 `main`，并授权执行 `S02-T06`；不授权 `S02-T07`，不授权 push。workflow policy 报告 T06 risk=`MEDIUM`、human gate=`key-checkpoint`、verification=`targeted`。
- **Implementation**：新增 deterministic `Slice2RecommendationService` 与 `Slice2TraceSink`，用现有 `TurnRequest`、ConstraintPatch/NormalizedConstraint、Variant-level eligibility、SOFT preference ranking 和 `RecommendationCandidateSet` 打通单轮推荐闭环。服务在不扩展公共 `AnswerEnvelope` 的前提下返回 top recommendation 的 ANSWER envelope，保留实际 Product/Variant identity、ProductCard、claims、Evidence、bindings 和 freshness；unsupported input、无候选、空商店和 partial commerce 均 fail closed 为安全 fallback。
- **Changed paths**：`backend/agent/__init__.py`；`backend/agent/recommendation.py`；`tests/integration/test_s02_t06_recommendation_flow.py`；`tests/e2e/test_s02_t06_recommendation_api.py`；`changes/slice-02-single-turn-recommendation/tasks.md`。
- **First failure and fix**：首次 targeted tests exit 0（7 passed）。首次 Ruff exit 1，原因是 `backend/agent/recommendation.py` 中 4 个未使用导入，以及两处测试长行；删除未使用导入并折行后，Ruff lint 通过。随后首次 format check exit 1，两份新测试需格式化；执行 `ruff format` 后通过。
- **Targeted verification**：`uv run pytest tests/integration/test_s02_t06_recommendation_flow.py tests/e2e/test_s02_t06_recommendation_api.py -q` exit 0（7 passed）。
- **Policy verification**：`python .agents/skills/drone-slice-workflow/scripts/check_scope.py S02-T06 --repo .` exit 0（`ok: true`，MEDIUM，无 disallowed/core/dependency/forbidden path）；`python .agents/skills/drone-slice-workflow/scripts/verify_task.py S02-T06 --repo .` exit 0（`ok: true`，policy-selected integration or e2e：48 passed, 234 deselected）。
- **Static/lock/full verification**：`uv lock --check` exit 0；`uv run ruff check .` exit 0；`uv run ruff format --check .` exit 0；`git diff --check` exit 0；`uv run pytest -q` exit 0（282 passed）。
- **Acceptance coverage**：happy path 返回 top recommendation；无匹配、unsupported input、partial commerce 和空/未知商店均不生成推荐 claims；ProductCard、resolved scope、Evidence、Claim binding 与实际推荐 Variant 一致；跨商店 fixture 只使用请求商店数据；trace 共享 correlation ID，fallback 路径不产生 ANSWER；未引入 Shopify 写调用、真实网络、模型、多轮 state 或新依赖。
- **Limitations**：本轮仅返回 top candidate 的公共 `AnswerEnvelope`，不扩展公共 schema 为多卡推荐列表；候选集合仍由 T05 contract 在内部表达。未实现 T07 完整 Verification Matrix、真实 Shopify/model、RAG、多轮状态、正式 Widget、比较或 Slice 3～7。
- **Recommended Next Task**：先完成 `S02-T06` snapshot、independent AI Review 和 MEDIUM key-checkpoint；经 Human 决策后才可进入 `S02-T07`。

## 4. Human Escalation

任一 Task 触发公共 Contract、Product Behavior、Architecture Boundary、Accepted Decision、主要依赖、真实外部服务或后续 Slice 扩展时，立即停止并请求 Human Decision。局部 fixture、私有函数和测试组织不需要审批。

## 5. Planning Approval Record

- Slice 1 Completion Evidence：Human accepted at HEAD `e1ca844554e3da0fd8d061dff55e149293a1dde3`。
- Slice 2 Planning：Human Final Approval accepted by current user context on 2026-08-30，覆盖目标、Scope、Acceptance 和 T01～T07。
- Slice 2 Implementation：当前 Human 上下文已授权并完成 `S02-T01`、`S02-T02`、`S02-T03`、`S02-T04`、`S02-T05` 与 `S02-T06`；`S02-T07` 仍未授权。
- Workflow Simplification：已形成受保护主线 baseline `d23c988e6c523e879c718c51474ae13d348d5c14`，implementation gate satisfied。
- Slice 2 Task Policy：已配置；S02-T01～S02-T06 scope/verification gate 通过。
- Push：not authorized。
- Real Shopify smoke：independent authorization required; non-blocking。
- Human Final Approval of this plan/tasks：SATISFIED。
