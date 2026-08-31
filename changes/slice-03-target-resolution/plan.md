# Slice 3 Planning — Target Resolution 与最小上下文状态

> 状态：DRAFT / Awaiting Human Review
>
> 本文件只定义 Slice 3 的 Product Behavior、Architecture Boundary、Acceptance 与有序实现计划。
> 当前不授权 Implementation、Task 状态推进、snapshot、commit、integration 或 push。

## 1. Readiness 与当前阶段

规划前实际检查结果：

| 检查 | 结果 |
|---|---|
| Planning Session worktree | `/Users/russeell/.codex/worktrees/1913/消费级无人机智能导购Agent` |
| 当前 HEAD | `a8bf4f4369e8b349133837f334da9ffd0b176cfb`，detached |
| 主工作区 | `/Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent`，`main` 同样位于 `a8bf4f4369e8b349133837f334da9ffd0b176cfb` |
| 初始工作区状态 | 当前 worktree 与主工作区均干净；无 staged / tracked / untracked 差异 |
| Slice 1 | `CLOSED`；T01～T09 全部 `DONE`，Completion Evidence 已接受 |
| Slice 2 | T01～T07 全部 `DONE`；当前无 active / executable Task |
| Slice 3 | 开始前不存在 planning artifact、Task policy 或 Implementation Record；未进入 Implementation |
| Workflow mode | 仅使用 `status` / `reconcile` 思路；未执行 run-next、snapshot、review、checkpoint 或 integrate-approved |

结论：Readiness 通过，可以进行本轮 Human 已授权的 Markdown Planning Reconciliation。该结论不构成 Slice 3 Implementation authority。

## 2. Reconciliation Summary

### Discovery

现有 Product Spec 与 Architecture 只使用宽泛的 `current_product_context / current_variant_context`，未区分：

- Page Context：当前页面和已选套装；
- Turn Target：本轮实际询问的单个对象、比较集合、推荐任务或全站支持意图；
- Conversation Context：用户已确认、可被后续代词继承的长期对象。

同时，原 Slice 3 路线聚焦完整多轮约束 State，无法单独约束临时跨产品提问、明确切换和比较/推荐路由边界。

### Impact

若不协调，Page Context 可能覆盖显式对象，临时跨产品问题可能污染长期状态，比较可能被折叠成单商品切换，推荐可能被页面商品限制，且 Answer、Card、Evidence、bindings 与动态事实可能指向不同对象。

### Classification

- Product Behavior、V1 Acceptance、Slice 路线：`docs/PROJECT_SPEC.md`。
- State / Router / TargetResolution / AnswerEnvelope / Trace 核心语义：`docs/ARCHITECTURE.md`。
- 三层上下文的候选取舍：`docs/DECISIONS.md` 的 DEC-012，目前是 `PROPOSED / PENDING HUMAN REVIEW / CANDIDATE DECISION`。
- 本 Slice 的局部 Scope、Acceptance、Tasks 与 Verification：本文件及 [tasks.md](./tasks.md)。
- 参考项目知识未变化，`docs/REFERENCE_ANALYSIS.md` 不需要修改。

### Recommendation and authority

采用最小三层模型与固定优先级；不在 Slice 3 内建设完整比较、推荐、RAG、长期数据库或复杂记忆。上述核心 Artifact 更新属于本轮 Human 明确授权的 Planning Reconciliation；DEC-012 只有在 Human 接受 Planning Baseline 后才可视为 accepted。实现仍须 Human Review、Planning Baseline 与单独的 S03-T01 authority。

## 3. Goal

在保留商品页默认上下文便利性的同时，建立一个可重复验证的目标解析闭环：系统从显式 Product / Variant、已确认 Conversation Context 与 Page Context 中得到本轮 Turn Target；临时跨产品问答只影响本轮；明确切换或确认切换才更新长期上下文；比较、推荐与全站支持只完成正确分类和移交；所有输出对象与证据严格绑定 Turn Target。

## 4. Scope

### 4.1 In scope

- Page Context、Turn Target、Conversation Context 与 pending switch 的最小、可审计状态语义。
- store-scoped 的显式 Product / Variant 名称或受控 alias 识别结果到身份的确定性解析。
- 固定优先级：显式 Product / Variant > 已确认 Conversation Context > Page Context > 澄清。
- “这款 / 它 / 这个 / 这个套装”等代词继承当前最高优先级明确上下文。
- 单次临时跨产品问答不修改长期上下文。
- 明确“切换到 X”或确认 pending switch 后，更新 Conversation Context。
- 比较集合、推荐任务、全站支持的路由分类与 typed handoff boundary；混合来源比较若无法记录 per-member provenance，本 Slice 必须澄清。
- Answer、Card、Evidence、claim bindings、动态事实 scope 与 target display 的一致性规划。
- 最小 revision、message idempotency、state diff 和 trace，限于目标切换行为。
- deterministic fixtures 与 Unit / Contract / Integration / E2E journey matrix。

### 4.2 Explicit non-goals

- 完整 ConstraintState 的新增、修改、撤回、跳过、冲突合并或连续澄清闭环。
- 完整比较引擎、Variant 代选、比较表或比较结论生成。
- 完整推荐候选、排序、推荐文案或 multi-product Evidence retrieval。
- Product RAG、文档摄取、Query Rewrite、Reranker、Milvus 或开放网络搜索。
- MongoDB / Redis 接入、长期数据库状态、跨会话记忆或复杂多轮记忆系统。
- 真实 Shopify 集成扩展、写操作、真实模型 CI 依赖或外部托管服务。
- Agent Framework、开放式 Multi-Agent、生产级 Widget、正式流式协议。
- Slice 4+ 行为、生产部署、commit、push 或 integration。

## 5. Product Behavior

### 5.1 Context definitions

- **Page Context**：TurnRequest 携带的当前页面 `product_id + optional variant_id`。`store_id` 属于 `TurnRequest` 顶层强制边界，不属于 PageContext。bundle 只可作为 Slice-local internal resolution detail 或未来 public Contract proposal；当前 public PageContext wire schema 不支持 bundle 字段。Page Context 只提供本轮默认，不自动成为长期状态。
- **Turn Target**：本轮真正要处理的 `SINGLE_OBJECT`、`COMPARISON_SET`、`RECOMMENDATION_TASK`、`STORE_SUPPORT` 或 `NEEDS_CLARIFICATION`。
- **Conversation Context**：用户明确切换或确认后保存的 Product / optional Variant；后续代词可继承它。

### 5.2 Resolution and mutation rules

```text
用户显式指定的 Product / Variant
        > 已确认 Conversation Context
        > 当前 Page Context
        > NEEDS_CLARIFICATION
```

- 显式其他商品覆盖 Page Context，但默认 `context_action=KEEP`，只改变当前 Turn Target。
- “切换到 X”在唯一、store-scoped 解析成功后可直接产生 `SWITCH_CONFIRMED`；对 pending switch 的肯定确认也可产生该 action。
- 普通“X 的价格呢？”不是切换指令，不能更新 Conversation Context。
- Product 或 Variant 解析为零个或多于一个候选时返回澄清；不得取目录第一项、默认项或最便宜项。
- Page Context 自身发生变化不等于 Conversation Context 已确认变化。
- 若已有 confirmed context，代词优先继承它；没有 confirmed context 时才继承 Page Context。
- 比较保留多个对象，不写入单个 confirmed context；推荐形成全店候选任务，不以 Page Context 作为候选过滤；全站支持不伪装成商品事实查询。
- “比较它和 Air 3S”这类混合来源比较必须逐成员记录 provenance，例如 confirmed/page-derived member 与 explicit member；若 T01 无法在 Slice-local proposal 中稳定表达 per-member provenance，则本 Slice 对该类请求返回澄清，不得用单值 `resolution_source` 假装覆盖整个比较集合。

### 5.3 Output identity

- 单对象回答的 resolved scope、Answer、Product Card、Evidence、claim bindings、动态 commerce ToolResult 与 target display 必须完全一致。
- 比较/推荐/支持在本 Slice 只返回 route/handoff，不生成尚未实现的比较、推荐或 RAG 结论。
- Client / Widget 最小显示语义为“正在回答：{Product title}{optional Variant label}”。若需要显示 bundle label，只能来自内部 resolution detail 或版本化 Contract proposal，不能暗示当前 PageContext wire schema 已支持 bundle。歧义时显示澄清，不显示猜测对象。

## 6. Acceptance

| ID | Acceptance | PASS 条件 |
|---|---|---|
| S3-A01 | Page default | 无显式对象、无 confirmed context 的代词问题使用同 store 的 Page Context。 |
| S3-A02 | Explicit override | 用户显式指定其他 Product 时，本轮 Turn Target 使用该对象，Page Context 不得覆盖。 |
| S3-A03 | Explicit Variant | 唯一显式 Variant 保留完整 store/product/variant 归属；foreign 或不属于 Product 的 Variant fail closed。 |
| S3-A04 | Confirmed inheritance | 已确认 Conversation Context 存在时，“它/这款/这个套装”继承 confirmed context，而非不同的 Page Context。 |
| S3-A05 | Temporary isolation | 单次跨产品事实问题只改变 Turn Target；resulting state revision 与 confirmed context 不发生无理由变化。 |
| S3-A06 | Explicit switch | 唯一解析成功的“切换到 X”直接确认时 `SWITCH_CONFIRMED` 恰好增加一次 revision；需要用户确认时 `AWAIT_CONFIRMATION` 创建 pending switch 并恰好增加一次 revision；确认成功后再恰好增加一次 revision，后续代词继承 X。 |
| S3-A07 | Ambiguity | Product / Variant 为零个或多于一个候选时 `NEEDS_CLARIFICATION`，不读取动态事实、不选择第一项、不更新 confirmed context。 |
| S3-A08 | Comparison boundary | 二至四个明确对象形成 `COMPARISON_SET` handoff；每个 member 必须有自己的 source/provenance；混合来源无法表达时返回澄清；不折叠为单对象，不写入 confirmed context，不生成完整比较。 |
| S3-A09 | Recommendation boundary | 推荐意图形成 `RECOMMENDATION_TASK` handoff；Page Context 不能把候选限定为当前商品，不实现排序。 |
| S3-A10 | Support boundary | 全站售前/售后支持意图形成 `STORE_SUPPORT` handoff 或安全 fallback；不伪造当前商品事实。 |
| S3-A11 | Output scope | 单对象 Answer、Card、Evidence、bindings、动态事实和 target display 全部绑定 Turn Target；Page Context 商品事实不得混入。 |
| S3-A12 | Revision / idempotency | stale `expected_revision` 返回可恢复冲突；重复 `message_id` + 相同 payload 返回已记录结果且不重复增加 revision；重复 `message_id` + 不同 payload fail closed；确认、否定、无关回复、新切换和过期 pending switch 均有确定处理。 |
| S3-A13 | Trace | 同一 correlation ID 可关联 Page Context、previous confirmed context、explicit refs、Turn Target、single-object resolution source 或 comparison member provenance、context action、state diff、route 与输出。 |
| S3-A14 | No scope expansion | Shopify write count=0；无完整比较/推荐/RAG/数据库/复杂记忆/正式 Widget；公共 Contract 若需版本化变化先停在 Human checkpoint。 |

## 7. Minimal Contracts / State Semantics

以下是计划语义，不是本轮对代码或公共 wire schema 的修改。

### 7.1 PageContext

- `product_id`
- optional `variant_id`

PageContext 由请求提供，只在当前 Turn 有效。只读核对当前实现：`backend/common/contracts.py` 中 `TurnRequest` 顶层包含 `store_id`，`PageContext` 只包含 `product_id` 与 optional `variant_id`，wire model 使用 `extra="forbid"`。因此不得把 `store_id` 或 bundle 移入或复制进 PageContext，除非 S03-T01 明确提出版本化 public Contract change 并停在 Human checkpoint。bundle 若被需要，只能作为 Slice-local internal resolution detail，不属于当前 public wire schema。

### 7.2 ConfirmedTargetContext

- `store_id`
- `product_id`
- optional `variant_id`
- `confirmed_by_message_id`
- `confirmed_at_revision`

不得保存动态价格、库存或可售状态。

### 7.3 TargetResolution

- `explicit_references`
- `resolution_source`: 单对象为 `EXPLICIT | CONFIRMED_CONTEXT | PAGE_CONTEXT | UNRESOLVED`
- `comparison_member_provenance`: 比较集合每个 member 各自的 `EXPLICIT | CONFIRMED_CONTEXT | PAGE_CONTEXT` 来源；混合来源不能压缩成单值 `resolution_source`
- `turn_target`
- `context_action`: `KEEP | AWAIT_CONFIRMATION | SWITCH_CONFIRMED`
- optional `clarification_reason / candidates`

### 7.4 TurnTarget

- `SINGLE_OBJECT`：一个 store-scoped Product 与 optional Variant。
- `COMPARISON_SET`：二至四个明确对象，每个 member 保留 identity 与 provenance；对象不明确或无法表达 per-member provenance 时整体进入澄清。
- `RECOMMENDATION_TASK`：保留用户条件和全店候选语义，不携带 Page Context 限制。
- `STORE_SUPPORT`：全站支持 intent 与可移交信息。
- `NEEDS_CLARIFICATION`：稳定 reason、候选摘要和一个澄清问题。

### 7.5 PendingTargetSwitch

- `target`: store-scoped Product / optional Variant identity。
- `created_by_message_id`
- `created_at_revision`
- `expected_revision`
- `source_turn` / triggering utterance category，例如 `SYSTEM_DISAMBIGUATION`、`USER_SWITCH_REQUEST` 或 `USER_CORRECTION`。
- `expires_after_turns` 或等价 expiration rule。
- replacement rule：新的明确切换请求可替换旧 pending switch，并产生新的 revision。
- cancellation rule：用户否定、显式取消、过期或 stale revision 冲突清除或拒绝 pending switch，必须有可回放 diff。

### 7.6 Minimal state transition

```text
(state_revision, confirmed_context, pending_switch)
  + (message_id, expected_revision, TargetResolution)
  -> (same state | next revision + explicit diff | recoverable conflict)
```

当前已实现 public `TurnRequest` 没有 `state_revision` / `expected_revision` 字段，且 `extra="forbid"` 禁止客户端临时透传未知字段。因此，客户端提交 `expected_revision`、服务端返回 resulting revision、recoverable conflict 或 idempotent replay result 都必须在 S03-T01 作为版本化 Contract proposal 明确提出，并以 HIGH-risk Human checkpoint 停止；Planning 不假定现有 wire schema 已能表达这些语义。

reducer 内部语义仍须固定：只有提交的 `expected_revision` 与当前 state revision 匹配时才能应用状态变更。`KEEP` 不更新 confirmed context、pending switch 或 revision。`AWAIT_CONFIRMATION` 创建、替换或清除 pending switch 时必须增加 revision；无状态 diff 的澄清回答不增加 revision。`SWITCH_CONFIRMED` 才能更新 confirmed context，并恰好增加一次 revision。

重复 `message_id` + 相同 payload 返回首次处理结果且不增加 revision。重复 `message_id` + 不同 payload fail closed。stale `expected_revision` 返回可恢复冲突且不覆盖 confirmed context。用户肯定确认 pending switch 时，`expected_revision` 必须匹配 pending switch 记录；否定或取消清除 pending switch；无关回复默认保持 pending switch，直到 expiration rule 触发；再次提出新切换按 replacement rule 处理。

Slice 3 可用 in-memory repository / reducer 验证语义，不接入 durable database。

### 7.7 Route and output boundary

- RouteDecision 必须消费已解析 Turn Target，不自行重写目标。
- 只有 `SINGLE_OBJECT` 可进入现有 Product Fact flow。
- 其他 target kinds 只产生 typed handoff / fallback，不执行 Slice 4+ 能力。
- expected revision、target display、handoff、resulting revision、conflict 或 replay semantics 需要改变公共 TurnRequest / AnswerEnvelope / RouteDecision wire schema 时，Implementation 必须先提交最小版本化 Contract proposal 并停在 S03-T01 Human Review；当前 Planning 不修改公共 Contract，也不得隐含突破现有 `extra="forbid"`。

## 8. Ordered Implementation Tasks

完整 Scope、risk、verification 与停止条件见 [tasks.md](./tasks.md)。顺序如下：

1. `S03-T01` — Target Resolution contract 与 golden matrix baseline。
2. `S03-T02` — 最小 confirmed context、revision 与 idempotent reducer。
3. `S03-T03` — store-scoped 显式 Product / Variant reference resolution。
4. `S03-T04` — Turn Target precedence、临时问答与确认切换。
5. `S03-T05` — 单对象 Target Resolution 接入现有 Product Fact flow 的 Walking Skeleton。
6. `S03-T06` — 比较 / 推荐 / 全站支持 typed routing handoff。
7. `S03-T07` — Slice 3 Verification Matrix 与 Completion Evidence。

不得并行执行、跳序或因前一 Task 完成而自动进入下一 Task。风险层级与 Human gate 必须在 Implementation 前写入并批准 workflow Task policy。

## 9. Verification Matrix

| Matrix | Journey | Expected | Primary level |
|---:|---|---|---|
| 1 | 商品页问“这款续航多久”且无 confirmed context | Page Context -> SINGLE_OBJECT | Unit + E2E |
| 2 | Mini 页面问“Air 3S 多少钱” | Air 3S Turn Target；Mini context 不变 | Integration + E2E |
| 3 | 临时问 Air 3S 后再说“它呢”且 confirmed context 是 Mini | “它”仍指向 Mini | State + E2E |
| 4 | “切换到 Air 3S”后再说“它多少钱” | revision 更新；后续指向 Air 3S | Contract + E2E |
| 5 | pending switch 后“是的” | 恰好一次 confirmed update；重放幂等 | Unit + Integration |
| 6 | 同名 Product 或 Variant 不唯一 | NEEDS_CLARIFICATION；zero dynamic reads | Unit + E2E |
| 7 | foreign / wrong-parent Variant | fail closed；不跨 Product 回退 | Contract + Integration |
| 8 | “比较 Mini 4 Pro 和 Air 3S” | COMPARISON_SET handoff；每个 member provenance 独立；无 context mutation | Router + E2E |
| 8b | confirmed/page context 为 Mini 时问“比较它和 Air 3S” | per-member provenance 可表达则 handoff；否则 NEEDS_CLARIFICATION | Router + E2E |
| 9 | “预算 7000 推荐一款”位于 Mini 页面 | RECOMMENDATION_TASK；不加 Mini 过滤 | Router + E2E |
| 10 | 全站售后/支持请求 | STORE_SUPPORT handoff / safe fallback | Router + E2E |
| 11 | 跨产品动态事实 | ToolResult、Evidence、Answer、Card、binding、display 均为 Turn Target | Contract + Integration |
| 12 | Page Context Evidence 注入跨产品答案 | INTERNAL_CONSISTENCY_ERROR；无事实 Answer | Unit + E2E |
| 13 | stale revision / duplicate message | 可恢复冲突 / 幂等结果；不覆盖 confirmed context | Contract + Integration |
| 14 | trace / zero-write / forbidden capability scan | 完整 target-resolution trace；zero writes；无后续 Slice 实现 | Operational + diff review |

每个 Implementation Task 仍须运行当时 policy 选择的 targeted gate、immutable snapshot 与独立 AI Review；本规划中的命令和矩阵不是已运行的验证证据。

## 10. Human Escalation Conditions

出现以下任一情况立即停止受影响 Task：

- 需要改变本文件 S3-A01～S3-A14、V1 Product Behavior、优先级或确认切换规则。
- 需要改变 Product / Variant / Store identity、UNKNOWN、动态事实或 Evidence scope 语义。
- 需要修改现有公共 TurnRequest、AnswerEnvelope、Evidence、ToolResult、RouteDecision wire schema；先提供版本化最小 proposal。
- 需要默认选择第一个 Product / Variant、按模糊分数越过歧义或让 Page Context 覆盖显式对象。
- 需要把比较、推荐、RAG、长期数据库、复杂 ConstraintState、正式 Widget 或 Slice 4+ 能力纳入实现。
- 需要新增主要依赖、真实 Shopify / 模型 / 外部服务作为 CI 前提、Shopify 写操作或 Agent Framework。
- 需要修改 Accepted Decision、Architecture Boundary、workflow safety gate 或 task-scope policy 例外。
- 发现完整多轮约束生命周期没有明确后续承接位置；应在 Slice 3 Completion Review 后做 roadmap reconciliation，不得在本 Slice 顺手实现。

## 11. Open Decisions

- `OD-S03-01` — Product / Variant alias baseline：建议只采用 normalized exact name + 明确受控 alias；任何多候选都澄清。fuzzy threshold 待代表性数据验证。
- `OD-S03-02` — target display wire 形状：优先复用现有 resolved scope / Product Card；若客户端无法稳定显示，提出最小版本化字段并 Human Review。
- `OD-S03-03` — pending switch UX：显式“切换到 X”可直接确认；系统主动询问产生的 pending switch 只在肯定确认后写入。
- `OD-S03-04` — state repository：Slice 3 先用可替换 in-memory repository 验证 revision / idempotency；MongoDB / Redis 接入时点保持开放。
- `OD-S03-05` — typed handoff payload：比较集合、推荐任务和支持意图的最小字段由 T01 提案；不得提前实现消费者能力。
- `OD-S03-06` — Query Rewrite：保持 DEC-001 默认关闭；即使未来启用，也只能产出辅助查询，不能覆盖原文、Turn Target 或 Conversation Context。
- `OD-S03-07` — 完整多轮 ConstraintState 的后续承接：保留为 V1 必需行为；在 Slice 3 Completion Review 后由 Human 决定新增中间 Slice、调整后续编号或其他明确路线。

## 12. Entry and Completion Conditions

进入 `S03-T01` 前必须同时满足：

- Human Review 接受本 plan、[tasks.md](./tasks.md) 以及本轮核心 Artifact reconciliation。
- 创建并集成一个仅含批准 Planning Artifact 的 Planning Baseline commit。
- workflow policy 已配置 S03-T01～T07 的 scope、risk tier、verification mode 与 completion task，并通过安全回归。
- 当前 worktree 干净、基线 commit 明确，当前 Human 上下文单独授权 HIGH-risk `S03-T01`。

Slice 3 只有在 T01～T07 全部 `DONE`、S3-A01～S3-A14 全部有可回放证据、独立 Slice review 完成并由 Human 接受 Completion Evidence 后才可关闭。关闭 Slice 3 不代表完整多轮 ConstraintState、Slice 4+ 或 push 已获授权。
