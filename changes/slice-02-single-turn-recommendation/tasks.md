# Slice 2 Ordered Implementation Tasks

> 状态：APPROVED / Implementation gated by Workflow Simplification
> 执行设计：[plan.md](./plan.md)
> 本文件定义的目标、Scope、Acceptance 和 T01～T07 已获 Human Final Approval；当前仍不授权实现。

## 1. Naming and Status

Slice 2 的文件路径已经包含 `slice-02`；任务在本文件内使用 `T01`～`T07`，完整引用使用 `S02-T01`～`S02-T07`。这样既兼容仓库现有 workflow 的局部 Task ID，又不会与 Slice 1 的 T01～T09 混淆。

任务状态仅使用：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`DONE`。

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | S02 数据/目录最小映射 | NOT_STARTED | Slice 1 closed; Slice 2 plan approved; Workflow Simplification baseline |
| T02 | S02 单轮 ConstraintPatch 与规范化 | NOT_STARTED | T01 |
| T03 | S02 Variant-level HARD eligibility | NOT_STARTED | T02 |
| T04 | S02 SOFT preference baseline | NOT_STARTED | T03 |
| T05 | S02 Product-grouped recommendation contract | NOT_STARTED | T03, T04 |
| T06 | S02 单轮推荐 Walking Skeleton | NOT_STARTED | T05 |
| T07 | S02 Verification Matrix 与 Completion Evidence | NOT_STARTED | T06 |

当前没有获授权的 Coding Task。Human 已批准 Slice 2 Planning，但 Implementation 必须等待 Workflow Simplification 通过独立 AI Review、Human 批准并形成干净基线，同时完成 Slice 2 Task Policy；不得因为 T01 的产品依赖已满足而自动执行。

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

各 Task 开始后才填写真实的 start commit、changed paths、命令/exit code、结果位置、修正、发现和限制。当前没有执行记录；Workflow Simplification 和 Slice 2 Task Policy 落地前，没有任何 Task 被授权开始。

## 4. Human Escalation

任一 Task 触发公共 Contract、Product Behavior、Architecture Boundary、Accepted Decision、主要依赖、真实外部服务或后续 Slice 扩展时，立即停止并请求 Human Decision。局部 fixture、私有函数和测试组织不需要审批。

## 5. Planning Approval Record

- Slice 1 Completion Evidence：Human accepted at HEAD `e1ca844554e3da0fd8d061dff55e149293a1dde3`。
- Slice 2 Planning：Human Final Approval accepted by current user context on 2026-08-30，覆盖目标、Scope、Acceptance 和 T01～T07。
- Slice 2 Implementation：not authorized。
- Workflow Simplification：required before Implementation；尚未独立 AI Review、Human 批准或提交。
- Slice 2 Task Policy：required before Implementation；尚未配置。
- Push：not authorized。
- Real Shopify smoke：independent authorization required; non-blocking。
- Human Final Approval of this plan/tasks：SATISFIED。
