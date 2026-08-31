# Slice 3 Ordered Implementation Tasks

> 状态：DRAFT / Awaiting Human Review
>
> 执行设计：[plan.md](./plan.md)
>
> 当前所有 Task 均未开始；本文件不是 Implementation authority。不得执行、snapshot、commit、checkpoint、integrate 或 push。

## 1. Naming and Status

任务状态仅使用：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`DONE`。

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Target Resolution contract 与 golden matrix baseline | NOT_STARTED | Human-approved Planning Baseline + S03 workflow policy |
| T02 | 最小 confirmed context、revision 与 idempotent reducer | NOT_STARTED | T01 |
| T03 | store-scoped 显式 Product / Variant reference resolution | NOT_STARTED | T01 |
| T04 | Turn Target precedence、临时问答与确认切换 | NOT_STARTED | T02, T03 |
| T05 | 单对象 Target Resolution 接入现有 Product Fact flow 的 Walking Skeleton | NOT_STARTED | T04 |
| T06 | 比较 / 推荐 / 全站支持 typed routing handoff | NOT_STARTED | T05 |
| T07 | Slice 3 Verification Matrix 与 Completion Evidence | NOT_STARTED | T06 |

风险层级只是 Planning proposal；Implementation 前必须由 Human 接受并写入 workflow Task policy。任何 Reviewer 识别出更高风险时向上升级。

| Task | Provisional risk | Planned Human gate |
|---|---|---|
| T01 | HIGH | per-Task Contract checkpoint |
| T02 | HIGH | per-Task state-semantics checkpoint |
| T03 | MEDIUM | key checkpoint |
| T04 | HIGH | per-Task Product Behavior checkpoint |
| T05 | HIGH | per-Task Product Fact integration checkpoint |
| T06 | MEDIUM | key typed-handoff checkpoint |
| T07 | HIGH | per-Task + Slice completion decision |

## 2. Task Details

### T01 — Target Resolution contract 与 golden matrix baseline

- **Goal**：把 Page Context、explicit references、confirmed context、TargetResolution、TurnTarget 与 context action 固化为最小可验证语义。
- **Scope**：Slice-local contract proposal、受控 Product / Variant alias fixture、golden journey manifest、Contract tests；优先复用现有 identity types。
- **Acceptance**：五种 TurnTarget kind、单对象 resolution source、comparison per-member provenance、三种 context action 与歧义语义可序列化/验证；`store_id` 仍位于 `TurnRequest` 顶层，当前 public PageContext 只含 product/variant；bundle 仅可作为 Slice-local internal resolution detail，若要进入 public PageContext 必须与 expected/resulting revision、conflict、replay 或 handoff 一样提交版本化 Contract proposal 并停在 Human Review；不得突破 `extra="forbid"`。
- **Verification**：Static + Contract + schema round-trip + fixture validation。
- **Dependencies**：Human-approved Planning Baseline；已配置并批准的 S03 workflow policy；当前上下文明确授权 T01。
- **Out of Scope**：state mutation、实体模糊模型、路由执行、API、Widget、比较/推荐消费者。
- **Human checkpoint**：任何公共 TurnRequest / AnswerEnvelope / RouteDecision 核心语义变化。

### T02 — 最小 confirmed context、revision 与 idempotent reducer

- **Goal**：实现仅服务目标确认/切换的最小 ConversationState reducer。
- **Scope**：confirmed target、pending switch、revision、message idempotency、state diff、in-memory repository 与 Unit/Contract tests。
- **Acceptance**：KEEP 不改 confirmed context、pending switch 或 revision；AWAIT_CONFIRMATION 创建/替换/取消 pending switch 时恰好增加一个 revision；SWITCH_CONFIRMED 恰好再增加一个 revision；duplicate `message_id` + 相同 payload 返回首次结果且不重复应用；duplicate `message_id` + 不同 payload fail closed；stale revision 返回可恢复冲突；不保存动态事实。
- **Verification**：Unit state-transition table + Contract stale/idempotency cases。
- **Dependencies**：T01。
- **Out of Scope**：完整 ConstraintPatch lifecycle、MongoDB、Redis、跨会话记忆、并发分布式锁。
- **Human checkpoint**：若实现必须接入 durable store、改变 Architecture state boundary 或公共 revision protocol。

### T03 — store-scoped 显式 Product / Variant reference resolution

- **Goal**：把已识别的显式名称/alias 确定性解析为当前 store 内唯一 Product / Variant identity。
- **Scope**：受控 catalog lookup/alias registry、Product / Variant ownership guard、零/多候选澄清结果、Unit/Integration tests。
- **Acceptance**：exact/controlled alias 唯一命中；foreign store、wrong-parent Variant、零命中、多命中均 fail closed；不得选择第一项；歧义路径不读取动态 commerce。
- **Verification**：Unit table + store isolation / ownership Integration。
- **Dependencies**：T01。
- **Out of Scope**：开放式搜索、embedding/fuzzy ranking、模型实体链接、真实 Shopify search expansion。
- **Human checkpoint**：需要 fuzzy threshold、默认选择或真实外部搜索才能继续。

### T04 — Turn Target precedence、临时问答与确认切换

- **Goal**：组合 T02/T03，实现固定优先级与明确状态更新边界。
- **Scope**：Target Resolver、代词继承、temporary override、explicit switch、pending confirmation、pending switch replacement / cancellation / expiration、traceable resolution reason 与 state patch。
- **Acceptance**：显式 > confirmed > page > clarify；临时跨产品只改变 Turn Target；明确/确认切换后才更新 confirmed context；Page Context 变化不自动写状态；肯定、否定、无关回复、再次提出新切换、过期、stale revision 与 duplicate message 行为可回放。
- **Verification**：Unit precedence matrix + Integration multi-turn scripts + revision/idempotency regression。
- **Dependencies**：T02、T03。
- **Out of Scope**：Query Rewrite、完整 constraint conversation、多目标比较执行、推荐排序。
- **Human checkpoint**：需要改变 Planning 中的候选优先级、切换规则或 DEC-012。

### T05 — 单对象 Target Resolution 接入现有 Product Fact flow 的 Walking Skeleton

- **Goal**：把 resolved SINGLE_OBJECT Turn Target 接入现有 Product Fact flow，并尽早证明最小端到端路径成立。
- **Scope**：Target Resolver -> existing fact service -> AnswerEnvelope / fallback -> minimal client harness；scope guard、target display 语义、Integration/E2E tests。
- **Acceptance**：Page default、explicit override、temporary question 和 confirmed switch 四类 SINGLE_OBJECT journey 可走通；跨产品事实只读取 Turn Target；Answer、Card、Evidence、bindings、freshness、display 与 Turn Target 一致；错 Page Context Evidence fail closed；zero writes。
- **Verification**：Contract identity gates + Integration current-commerce cases + E2E single-object temporary/switch journeys。
- **Dependencies**：T04。
- **Out of Scope**：生产 Widget、正式 UI、SSE、完整 compare/recommend/support、真实 Shopify/model。
- **Human checkpoint**：稳定显示目标或 resulting revision 必须扩展公共 AnswerEnvelope 时，先停在版本化 Contract Review。

### T06 — 比较 / 推荐 / 全站支持 typed routing handoff

- **Goal**：将非单对象意图安全分类并移交，不误入现有 Product Fact flow。
- **Scope**：COMPARISON_SET、RECOMMENDATION_TASK、STORE_SUPPORT 的最小 typed handoff、RouteDecision、boundary tests。
- **Acceptance**：比较保留二至四个对象且不更新单对象 context；比较 member 各自保留 provenance，无法表达“它 + 显式对象”等混合来源时返回澄清；推荐不携带 Page Context 过滤；支持不生成商品事实；所有 handoff 都不执行下游 Slice 4+ 能力。
- **Verification**：Router Unit + Contract + E2E boundary cases。
- **Dependencies**：T05。
- **Out of Scope**：比较表、Variant 代选、eligibility/ranking 扩展、RAG/售后答案生成。
- **Human checkpoint**：handoff 需要公共 Contract 变化、主要依赖或消费者实现。

### T07 — Slice 3 Verification Matrix 与 Completion Evidence

- **Goal**：覆盖 plan S3-A01～S3-A14 和 Matrix #1～#14，记录实际证据并停在 Slice Completion Review。
- **Scope**：tests / eval 的最小 replay manifest、Task Execution Record、必要且已批准的局部修正；不得新增产品能力。
- **Acceptance**：全部 Acceptance 有可定位的 PASS 证据；full suite、scope、identity、state revision、trace、secret、zero-write 与 forbidden-capability gates 通过；真实 smoke 明确记录但不作为 completion prerequisite。
- **Verification**：Static + Unit + Contract + Integration + E2E + full suite + diff/scope review。
- **Dependencies**：T06。
- **Out of Scope**：新业务行为、roadmap 重排实现、真实外部服务、Slice 4+、push。
- **Human checkpoint**：HIGH Task review + independent Slice review + Human Completion decision。

## 3. Planned Verification Mapping

| Acceptance | Primary owner | Required evidence |
|---|---|---|
| S3-A01～A03 | T03 / T04 | Page default、explicit Product/Variant、ownership 与 ambiguity matrix |
| S3-A04～A07 | T02 / T04 | confirmed inheritance、temporary isolation、switch、revision/idempotency tests |
| S3-A08～A10 | T06 | comparison/recommendation/support typed routing boundary tests, including mixed-source comparison provenance/clarification |
| S3-A11 | T05 | Answer/Card/Evidence/binding/freshness/display exact scope E2E |
| S3-A12～A13 | T02 / T04 / T07 | stale/duplicate replay 与 complete target-resolution trace |
| S3-A14 | T07 | full diff, zero-write, no-dependency/no-forbidden-capability evidence |

计划中的测试名称、命令和 pass count 都不是执行证据。Execution Record 只能填写实际运行的命令、exit code 与结果。

## 4. Execution Records

当前不存在 Execution Record。Human Review、Planning Baseline、workflow policy 与单独 Implementation authority 完成前，T01～T07 必须保持 `NOT_STARTED`。

## 5. Planning Approval Record

- Slice 1 Completion Evidence：accepted at `e1ca844554e3da0fd8d061dff55e149293a1dde3`。
- Slice 2 Tasks：T01～T07 在当前 `main` HEAD `a8bf4f4369e8b349133837f334da9ffd0b176cfb` 均为 `DONE`。
- Slice 3 Planning Reconciliation：本轮已创建，`DRAFT / Awaiting Human Review`。
- Slice 3 Planning Baseline commit：not created / not authorized in this Session。
- Slice 3 workflow Task policy：not configured / not approved。
- Slice 3 Implementation：not authorized；S03-T01 `NOT_STARTED`。
- Snapshot / checkpoint / integration / push：not authorized and not performed。

## 6. Recommended Next Step

Human 先审查以下文件及完整 diff：

- `docs/PROJECT_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- [plan.md](./plan.md)
- [tasks.md](./tasks.md)

若接受，下一 Session 才创建仅含批准 Planning Artifact 的 Planning Baseline commit，并配置/审查 Slice 3 workflow policy。完成这些前置条件后，Human 再单独授权 `S03-T01`；不得从本 Planning Session 直接进入实现。
