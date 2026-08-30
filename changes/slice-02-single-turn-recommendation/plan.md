# Slice 2 Planning — 单轮约束推荐

> 状态：APPROVED / Implementation gated by Workflow Simplification
> 本文件的目标、Scope、Acceptance 和 T01～T07 已获 Human Final Approval；当前仍不授权实现。
> Slice 1 已在 HEAD `e1ca844554e3da0fd8d061dff55e149293a1dde3` 关闭。

## 1. Planning Boundary

本 Slice 只验证一轮输入中的结构化约束如何形成候选推荐：

```text
TurnRequest
  -> deterministic ConstraintPatch
  -> normalized constraints
  -> Variant-level HARD eligibility
  -> transparent SOFT preference signals
  -> Product-grouped candidates
  -> recommendation reasons + Evidence
  -> AnswerEnvelope / safe fallback
```

本轮不实现正式 Widget、真实 Shopify 连接、持久化多轮状态或模型训练。

## 2. Source-of-Truth Check

- `docs/PROJECT_SPEC.md`：Slice 2 要求单轮预算/用途/重量/功能约束、最多三款商品、可售 Variant、无匹配解释和证据。
- `docs/ARCHITECTURE.md`：Constraint Manager 产生 Patch；Catalog/Constraint Engine 在 Variant 层做确定性资格；Agent/Router 不拥有候选真值；Composer 只表达通过验证的候选。
- `docs/DECISIONS.md`：DEC-006 的 Recommendation Ranking 仍为 OPEN；DEC-010 要求 HARD eligibility 在 Variant 层确定性执行；DEC-009 保持动态 commerce 与静态目录分层。
- Slice 1 contracts：`TurnRequest`、`ProductRecord`、`VariantRecord`、`AttributeValue`、`ToolResult`、`Evidence`、`AnswerEnvelope` 的既有语义不得被静默改写。

未发现需要修改四个核心 Artifact 的前置冲突。若实现需要改变既有公共 `AnswerEnvelope` 核心语义，必须停止并请求 Human Decision。

## 3. Product Behavior for This Slice

### In scope

- 解析一轮用户输入中的有限、可测试约束：预算上限、最大起飞重量、最低电池数，以及由当前受控 fixture 明确支持的少量字段。
- 将约束区分为 `HARD` 与 `SOFT`，保留字段、操作符、值、单位、来源 turn 和解析置信度/来源。
- 只让当前可售且通过所有已知 HARD 约束的 Variant 进入正式候选。
- `UNKNOWN`、缺失字段或不可确认的 HARD 条件不得视为满足。
- 以 Product 分组展示候选，但保留每个实际 Variant 身份。
- 最多返回三款不同 Product；同一 Product 不因多个 Variant 重复占位。
- 为每个候选提供满足的 HARD 条件、可解释的 SOFT 信号、关键取舍和对应 Evidence。
- 无候选时返回包含阻断约束或缺失信息的安全 fallback，不输出正式推荐。

### Explicit non-goals

- 多轮 ConstraintState、revision、撤回、跳过、冲突合并和持久化。
- 自然语言模型、开放式 Agent loop、学习排序、个性化或利润/库存去化排序。
- 文档 RAG、比较、跨商品文档检索和实时库存之外的 Shopify 写操作。
- 购物车、结账、订单、客户、正式 Widget、SSE/WebSocket、部署平台。

## 4. Minimal Proposed Contracts

这些是 Slice 2 实现需要稳定的最小语义，不是完整 V1 schema。

### 4.1 ConstraintPatch (single-turn subset)

- `source_turn_id`
- `operation`: `ADD`、`UPDATE` 或 `NO_CHANGE`；撤回/跳过属于 Slice 3
- `field`
- `operator`
- `value`
- `unit`
- `hardness`: `HARD` 或 `SOFT`
- `confidence` / `provenance`

无效类型、单位或操作符在应用边界拒绝；不得静默猜测单位。

### 4.2 NormalizedConstraint

规范化后的可比较条件：字段、规范化操作符、规范化值/单位、硬软属性、来源和状态。当前 Slice 不保存 durable revision。

### 4.3 EligibilityResult

- `store_id`
- `product_id`
- `variant_id`
- `eligible`
- `rejection_reasons`
- `evaluated_constraints`
- 当前 commerce snapshot 的 `observed_at`

任何 HARD 约束为 UNKNOWN、缺失、不可售或不满足时，`eligible=false`。

### 4.4 RecommendationCandidate

- 一个实际 Variant 的身份与 Product 展示信息
- `eligibility` 结果
- 透明的 SOFT match signals
- 关键理由与取舍
- 与 Product/Variant scope 对齐的 Evidence 和 claim bindings

### 4.5 Recommendation response

优先复用 Slice 1 的 `AnswerEnvelope` 身份、fallback、trace 和 evidence 语义。若需要新增 wire 字段或新的 outcome 才能表达候选列表，先在独立 Contract Task 中提出最小扩展并停在 Human Review；不得由实现 Agent 静默扩展公共 schema。

## 5. Data Baseline

- 使用受控、匿名的 synthetic catalog/commerce fixture；只纳入本 Slice 需要的 Product、Variant、属性和当前可售快照。
- 不把整个 Data Readiness pack、评估候选全集、文档语料或训练数据复制进仓库。
- 真实 Shopify 导入/导出/匿名映射与本 Slice 的 deterministic baseline 分开；真实 smoke 需单独授权，且不是 completion gate。
- 先使用已有字段（如价格、库存/可售状态、起飞重量、电池数）；新增字段只有在数据和 Contract 都明确需要时才加入。
- 数据必须维持 `store_id → product_id → variant_id` 归属、`KNOWN/UNKNOWN/NOT_APPLICABLE` 语义和 `observed_at` 传播。

## 6. Acceptance (PASS / FAIL)

| ID | 判据 | PASS 条件 |
|---|---|---|
| S2-A01 | 约束解析 | 一轮输入能生成可验证的字段、操作符、值、单位和 HARD/SOFT；不支持的输入安全降级。 |
| S2-A02 | HARD eligibility | 资格只在具体 Variant 判断；所有已知 HARD 条件满足且 Variant 当前可售才 eligible。 |
| S2-A03 | UNKNOWN/missing | HARD 所需字段 UNKNOWN 或缺失时不通过，不把 UNKNOWN 当 false/zero/unsupported。 |
| S2-A04 | Identity | 候选、Product card、Evidence、claim binding 与实际 Variant/Product/Store 一致。 |
| S2-A05 | No mixing | 不跨 Variant 拼接价格、重量、库存或属性；Product 分组不隐藏 Variant 身份。 |
| S2-A06 | Candidate cap | 正式推荐最多三款不同 Product；同一 Product 的多个 Variant 不占用多个 Product 名额。 |
| S2-A07 | SOFT transparency | SOFT 信号只用于可解释排序/取舍，不能覆盖 HARD 不满足；排序规则稳定可复现。 |
| S2-A08 | No-match fallback | 无 eligible Variant 时说明阻断条件或缺失信息，不输出正式推荐。 |
| S2-A09 | Evidence | 每个关键推荐理由和事实结论绑定到同一 Product/Variant scope 的 Evidence。 |
| S2-A10 | Dynamic facts | 价格、库存、可售状态来自当前 Shopify ToolResult，并保留 `observed_at`；不从静态目录或旧结果冒充当前事实。 |
| S2-A11 | Store isolation | 跨商店输入或数据不进入候选，安全 fallback 且 Shopify write count=0。 |
| S2-A12 | Contract/API | 请求、响应、fallback 和 trace correlation 保持公共 contract 一致；若需核心 schema 改变则停止升级。 |
| S2-A13 | Reproducibility | deterministic fixture 下相同输入、目录版本和配置产生同一候选顺序及理由。 |

## 7. Ordered Tasks (planning only)

任务编号采用“Slice 目录 + Slice 内局部编号”：文件路径 `slice-02-single-turn-recommendation` 表示 S02，任务表使用 `T01`～`T07`；对外引用写作 `S02-T01`，避免与 Slice 1 的 T01 混淆。

### T01 — S02 数据/目录最小映射

确定本 Slice 需要的匿名 Product/Variant 属性与 commerce fixture，验证字段状态、单位、可售性和身份归属。只纳入推荐所需最小数据；不导入真实数据、不创建训练集。

### T02 — S02 单轮 ConstraintPatch 与规范化

定义并实现有限字段的单轮解析、单位规范化、HARD/SOFT 分类和无效输入处理。不得实现多轮 state 或模型调用。

### T03 — S02 Variant-level HARD eligibility

实现确定性硬约束判断、UNKNOWN/missing fail-closed、可售性检查和结构化拒绝原因。不得加入软排序或模型判断。

### T04 — S02 SOFT preference baseline

实现透明、确定性的软偏好信号与排序基线；硬约束结果优先，权重保持局部且可替换。若需要选择长期 ranking 算法，升级 DEC-006 实验，不静默定案。

### T05 — S02 Product-grouped recommendation contract

组合候选、Product 分组、最多三款 Product、Variant 身份披露、理由/取舍和 Evidence binding。若需要改变公共 AnswerEnvelope，先停在 Human Decision。

### T06 — S02 单轮推荐 Walking Skeleton

打通 TurnRequest → constraints → eligibility → candidates → response/fallback → trace 的 deterministic E2E；验证无匹配、UNKNOWN、不可售、跨商店和零写调用。

### T07 — S02 Verification Matrix 与 Completion Evidence

补齐本 Slice Acceptance 的 Unit/Contract/Integration/E2E 矩阵，运行完整 gates，记录真实结果并停止在 Slice 2 Completion Review。

## 8. Verification Strategy

- T01：静态 schema/data validation + fixture unit。
- T02：ConstraintPatch contract + normalization unit。
- T03：eligibility unit/property-like table + integration。
- T04：ranking deterministic unit + tie/identity tests。
- T05：contract/evidence binding tests。
- T06：integration + E2E，覆盖 happy path 和 fallback。
- T07：完整 Matrix、scope、secret、zero-write、core Artifact zero-diff。

每个 Task 遵守：one bounded logical change → one validation → independent AI Review → policy-controlled local checkpoint。具体 checkpoint、Human gate 和跨 Session handoff 由经 Human 批准并提交的仓库 Workflow Policy 管理；该 Workflow Simplification 落地前，不创建自动 checkpoint，也不进入 Slice 2 Implementation。任何 Task 不得绕过顺序或自动扩大到下一个 Task。

## 9. Human Escalation Conditions

出现以下情况，停止当前工作并请求 Human Decision：

- 需要修改 Slice 2 Acceptance、V1 Product Behavior 或硬性质量门槛。
- 需要改变 Product/Variant/Store 身份或 UNKNOWN 语义。
- 需要改变 Slice 1 已接受的 `AnswerEnvelope`、Evidence、ToolResult 或 fallback 核心语义。
- 需要 MongoDB、Redis、队列、RAG、向量库、Agent Framework、托管服务或跨 Slice 主要依赖。
- 需要真实 Shopify 或模型成为 CI 前提，或执行任何 Shopify 写操作。
- 需要把软排序从透明 baseline 升级成学习排序或固定 DEC-006 未验证的权重。
- 需要扩大到多轮 State、比较、RAG、正式 Widget 或 Slice 3～7。

普通 fixture 形状、私有函数、局部测试组织和不改变公共语义的类型细化不需要额外审批。

## 10. Open Decisions

- `OD-S02-01`：ConstraintPatch 的最小自然语言解析覆盖范围；先用 deterministic vocabulary，真实模型适配留待后续实验。
- `OD-S02-02`：SOFT ranking 的字段权重和 tie-break；先以可解释规则 baseline，不宣称已优化。
- `OD-S02-03`：Product-grouped response 是否能复用当前 `AnswerEnvelope`，或需要最小版本化 recommendation payload；如影响公共 wire schema，必须 Human Review。
- `OD-S02-04`：缺失属性治理阈值；在代表性数据和 Eval 前不写死全局阈值。
- `OD-S02-05`：真实 Shopify Product/Variant/metafield 映射；需要自有测试店 Preview/只读 smoke 后确认。

## 11. Implementation Entry Conditions

进入 Slice 2 Implementation 前必须同时满足：

- Human Final Approval 已接受本文件与 `tasks.md`（已满足，2026-08-30）。
- Slice 1 Completion Evidence 已接受（已满足）。
- Workflow Simplification 已通过独立 AI Review、Human 批准并形成干净的本地基线 commit。
- `drone-slice-workflow` 已配置 Slice 2 Task Policy，且 workflow 安全回归通过。
- 当前工作区干净且基线明确。
- 满足以上条件后，S02-T01 是唯一允许被明确授权的起始 Task；当前未授权 T01～T07、Slice 3～7、push。
- 若 T05 发现公共 Contract 需要变化，先完成独立 Reconcile 和 Human Decision。

## 12. Completion Evidence (future)

Slice 2 只有在所有 Task 完成、Acceptance 全部 PASS、推荐候选与证据可回放、完整测试通过且 Human Review 接受 Completion Evidence 后才可关闭。真实 Shopify smoke 如未授权或未运行，明确记录为非阻塞，不得冒充 completion evidence。
