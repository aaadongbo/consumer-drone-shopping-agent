# 消费级无人机智能导购 Agent — ARCHITECTURE V1

> 状态：V1 Draft / Source of Truth for HOW
> 本文件描述当前实现设计，不重新定义产品范围与质量目标。产品行为以 [PROJECT_SPEC.md](./PROJECT_SPEC.md) 为准；实验性选择以 [DECISIONS.md](./DECISIONS.md) 为准。

## 1. Design Principles

1. **确定性规则负责资格，生成模型负责理解与表达。** 数值比较、单位换算、可售判断、硬约束过滤和变体归属不得交给模型自由推断。
2. **Variant 是资格判断单元，Product 是主要呈现单元。** 推荐与比较都必须保留实际变体身份。
3. **动态事实与文档知识分层。** Shopify 提供价格、库存、可售状态等当前事实；Catalog 保存规范化商品属性；RAG 处理手册、FAQ、描述与政策。
4. **状态更新与回答生成分离。** 原始对话不可替代结构化状态；每次状态变化必须可审计、可做并发保护。
5. **证据是结构化输出，不是提示词附属文本。** 检索、工具和目录都产生统一 Evidence，回答中的关键 claim 与其绑定。
6. **工具边界有界且只读。** Agent 只能在声明的能力和预算内调用工具，不运行开放式自治循环。
7. **失败是协议的一部分。** 无匹配、未知、不可售、超时和授权问题均使用稳定的失败语义。
8. **保持实现可替换。** 存储、向量引擎、模型供应商和传输协议通过 Contract 隔离，不成为产品 Requirement。
9. **Agentic 只用于受限补证。** 多步检索必须以 Turn Target、约束、allowlist 和 Evidence Gate 为边界，不能演变成开放式 ReAct 或多 Agent 自治。

## 2. System Context and Current Design Choices

### 2.1 Product requirements versus design choices

| 项目 | 当前定位 | 说明 |
|---|---|---|
| 正式 Shopify 店面聊天组件 | Product Requirement | 用户体验入口，必须满足 Spec 的可见状态、流式响应和证据展示行为 |
| TypeScript Widget | Current Design Choice | 适配 Shopify 前端生态；语言本身不是产品要求 |
| Python 3.12 + FastAPI | Current Design Choice | 与现有 RAG 资产、异步工具调用和类型化 API 生态匹配；并非不可替换 |
| 持久化、版本化会话状态 | Architecture Requirement | 多轮一致性、恢复、回放和并发控制所必需 |
| MongoDB 作为 durable source of truth | Current Design Choice | 适配可演进的会话与证据文档结构；若实现证据推翻此选择，可通过 Decision 替换 |
| Redis 用于缓存、短期协调和锁 | Current Design Choice | 降低热状态读取成本并保护并发 revision；不得成为唯一状态来源，且可在早期单实例 Slice 中延后接入 |
| 过滤式 hybrid retrieval | Architecture Direction | 商品范围、权限与身份过滤优先于生成；具体检索组合仍可实验 |
| Milvus | Open / Provisional Design Choice | 仅作为当前候选向量引擎，见 DEC-007 |
| MCP | Optional Adapter | 内部 Tool Contract 不依赖 MCP；需要外部标准化接入时再提供适配层 |
| OpenAI-compatible model adapter | Design Choice | 避免业务协议绑定单一模型供应商 |
| 流式交互 | Product/UX Requirement | 具体采用 SSE、分块 HTTP 或其他传输尚未锁定 |

已接受和开放选择的完整状态由 [DECISIONS.md](./DECISIONS.md) 维护。

## 3. Core Modules and Responsibilities

### 3.1 Storefront Widget

职责：

- 接收用户输入并展示流式或渐进式响应。
- 展示、编辑和撤回当前约束 chips。
- 渲染商品卡、变体说明、比较表、引用与 fallback 操作。
- 传递当前商品页的 product/variant context。
- 展示本轮实际回答对象，例如“正在回答：DJI Mini 4 Pro”，并区分页面对象与已确认的会话对象。
- 在会话恢复或 revision 冲突时展示明确状态。
- 提供重试、重置和联系人工支持等动作。

边界：Widget 不执行商品资格判断，不持有权威状态，不直接访问 Shopify 管理 API。

### 3.2 Conversation API

职责：

- 识别商店、会话、消息与 locale。
- 校验 TurnRequest 和 state revision。
- 协调单轮处理并返回结构化事件、最终 AnswerEnvelope 或错误。
- 执行身份、商店隔离、幂等和请求级超时策略。

边界：API 层不内嵌领域排序或 RAG 策略，只编排应用服务。

### 3.3 State and Constraint Manager

职责：

- 分离保存原始消息历史与派生 ConversationState。
- 将当前输入转换为 ConstraintPatch，并执行规范化、验证和冲突检查。
- 维护约束生命周期：新增、更新、撤回、跳过、重新激活。
- 维护 revision，拒绝或合并过期写入，支持回放与恢复。
- 记录 pending clarification、已确认的 Conversation Context、待确认切换、候选和比较集合；Page Context 仍是请求级输入，不因打开页面或临时提问自动写入长期状态。

边界：该模块决定“状态如何变化”，不决定哪些商品满足条件，也不生成最终自然语言。

### 3.4 Shopify Tool Layer

职责：

- 提供商店范围内的只读商品能力，包括商品搜索、商品详情、变体详情和动态 commerce 刷新。
- 将 Shopify 数据转换为内部类型，并保留 source、observed_at 和错误语义。
- 处理分页、限流、重试、超时、鉴权和商店隔离。
- 对所有调用执行 allowlist，拒绝任何写操作。

V1 最小能力集合：

- search_products
- get_products
- get_variants
- refresh_commerce_state

边界：Tool Layer 返回事实，不做对话路由、推荐排序或回答生成。MCP 若启用，只是该 Contract 的传输适配器。

### 3.5 Catalog and Constraint Engine

职责：

- 将 Shopify 商品、变体和商家补充属性规范化为统一目录。
- 规范化单位、枚举、字段别名与已知状态。
- 对每个可售 Variant 执行硬约束 eligibility 判断。
- 计算透明的软偏好匹配信号与未满足项。
- 为只给出 Product 的比较请求选择最符合当前约束的可售 Variant，并披露选择。
- 输出候选、拒绝原因和比较所需的规范化事实。

边界：Catalog 是结构化事实和确定性逻辑，不从长文档中自由生成属性，也不把 UNKNOWN 当作 pass 或 unsupported。

### 3.6 Product RAG

职责：

- 摄取商家授权的商品描述、官方手册、FAQ 与政策资料。
- 保留原始来源、文档版本、商品/变体范围和解析位置。
- 为指定商店与商品范围检索支持性片段，返回 Evidence 而不是直接回答。
- 支持索引版本、重复检测、删除或失效传播和离线评估。
- 为受限 ActionPlan 提供可复现的 baseline retrieval 与定向二次检索能力。

边界：RAG 不负责实时价格、库存或可售状态，不跨商品无约束检索，不以模型清洗结果替代原始证据。RAG 可被 Agent 请求补检，但不得自行修改目标、约束或最终 claim。

Chunking、Query Rewrite、Multi-product Retrieval 与 Reranker 的具体策略保持开放，见 DEC-001 至 DEC-004。Milvus 仍是可替换候选，见 DEC-007。

### 3.7 Agent and Router

职责：

- 基于当前 Turn 与 ConversationState 选择下一步动作。
- 通过有界 Target Resolver 将显式 Product / Variant、已确认 Conversation Context 与 Page Context 解析为本轮不可变 Turn Target；解析优先级为显式对象 > 已确认会话对象 > 页面对象 > 澄清。
- 将单对象、比较集合、推荐任务与全站支持意图区分为不同目标类型；比较集合不得折叠成单对象切换，推荐不得被 Page Context 限定。
- 仅在显式切换动作或切换确认后请求 State Manager 更新 Conversation Context；普通跨产品问答的目标只在本轮有效。
- 在有界策略内请求 Constraint Manager、Catalog、Shopify Tool 或 RAG 能力。
- 生成受限 ActionPlan 时只能选择 allowlist 动作，并受 round、latency、tool-call 和 token 预算约束。
- 控制澄清次数、工具预算、超时和 fallback。
- 输出可解释 RouteDecision。

V1 路由意图：

- DISCOVERY
- RECOMMENDATION
- REFINEMENT
- COMPARISON
- PRODUCT_QA
- POLICY_QA
- OUT_OF_SCOPE

边界：Router 不直接选择最终推荐商品，不自行进行数值判断，也不通过无限循环尝试工具。Target Resolver 只能解析已识别对象和目标类型；商品/Variant 歧义必须请求澄清，不能默认选择第一个。推荐候选由 Catalog/Constraint Engine 产生。ActionPlan 只能请求补证或澄清，不能放宽 HARD 条件、改变 identity 或把文档事实当作实时 commerce 事实。

### 3.7.1 Bounded ActionPlan

受限 Agentic RAG 使用单编排器内的顺序 ActionPlan，而不是开放式自治 Agent。最小闭环：

```text
Turn Target / Constraints
        -> bounded ActionPlan
        -> Shopify Read or Product RAG
        -> Evidence / Commerce Verification
        -> optional corrective round
        -> Evidence Gate
        -> Answer or Fallback
```

`max_action_rounds = 2 total`。第 1 轮包含 baseline 初始检索或读取；只有第 1 轮后的验证结果证明证据不足、动态事实缺失或需要澄清时，才允许第 2 轮 corrective action。因此不是“初始轮 + 两轮纠正”，最多只有一次纠正轮。

Provisional budget config：

| Key | Provisional hard limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |

这些数值是实验前默认硬上限，不是永久性能目标。任一预算耗尽时，当前 Turn 必须停止继续补证并返回可解释 fallback；不得继续调用工具、扩大范围或用模型常识补齐。

V1 allowlist action types：

- 对同一 store/product/variant 做定向二次文档检索。
- 调用只读 `refresh_commerce_state` 获取当前动态事实。
- 基于已有 Evidence 做 Derived Evidence 二次计算，并复核 HARD 条件。
- 请求澄清。

Slice 5 只能执行同一 Store/Product/Variant 范围内的 Product RAG baseline retrieval、一次定向二次检索或请求澄清。`refresh_commerce_state`、Derived Evidence 复算和 HARD recheck 是 Slice 6 的执行职责；它们可以作为全局 action type 被命名，但不得在 Slice 5 实现中执行。

ActionPlan 最多执行 `2` 轮 total；不得开放网络搜索、启动多 Agent、生成任意工具调用、跨店/跨商品扩展检索、修改用户约束或覆盖 Evidence Gate 的否决。

`ActionRoundTrace` 最小记录：

- `action_plan`：本轮计划、target scope、allowlisted action 和预算快照。
- `choice_reason`：为什么选择该动作或为什么停止。
- `observation`：工具或检索返回的结构化结果摘要。
- `verification_result`：scope、freshness、coverage、conflict 与 budget gate 的判定。
- `corrective_action`：若进入第 2 轮，记录触发原因和动作；否则为空。
- `budget_consumption`：round、tool call、deadline、retrieval token 和 model token 消耗。
- `final_stop_reason`：`ANSWER_READY`、`CLARIFICATION_REQUIRED`、`ACTION_ROUND_LIMIT`、`TOOL_CALL_LIMIT`、`TURN_DEADLINE`、`RETRIEVAL_TOKEN_BUDGET`、`MODEL_TOKEN_BUDGET` 或具体 failure reason。

### 3.8 Evidence and Response Composer

职责：

- 统一接收 Catalog、Shopify Tool、Document 和可验证 Derived Evidence。
- 将回答中的关键 claim 与 Evidence ID 绑定。
- 验证证据的 store/product/variant 归属、版本和新鲜度。
- 生成回答文本、约束 chips、商品卡、比较数据、引用和 follow-up。
- 在证据不足、动态事实过期或候选为空时生成标准 fallback。

边界：Composer 只能表达已通过上游验证的事实和候选，不可重新放宽硬约束或修改状态。

### 3.9 Evaluation and Trace

职责：

- 为每轮记录输入状态、ConstraintPatch、状态 diff、RouteDecision、工具调用、候选与拒绝原因、检索结果、Evidence、回答、fallback、版本和延迟。
- 支持离线回放、golden set、模块级评估和 E2E 评估。
- 记录模型、提示、目录、索引和决策版本，使结果可比较。
- 对敏感字段做脱敏，不记录令牌或密钥。

边界：Trace 是观测与评估数据，不作为 ConversationState 的权威来源。

## 4. Core Data Flow

```text
User Turn / Page Context + confirmed Conversation Context
        |
        v
Conversation API -- load revisioned state --> State Store
        |
        v
Target Resolver --> immutable Turn Target --> optional confirmed-context patch
        |
        v
Constraint extraction --> ConstraintPatch --> normalize / validate / conflict check
        |                                      |
        |                                      v
        |                              new ConversationState revision
        v
Agent / Router --> bounded action plan
        |
        +--> Shopify Tool Layer --> current commerce facts
        |
        +--> Catalog / Constraint Engine --> eligible variants + rejection reasons
        |
        +--> Product RAG --> scoped Evidence
        |
        +--> bounded action rounds, max 2 total, allowlist only
        |
        v
Evidence / Response Composer --> identity, freshness, constraint and citation validation
        |
        +--> persist state + trace
        |
        v
Structured / streamed AnswerEnvelope --> Storefront Widget
```

单轮并非每次调用所有模块。事实问答按 Turn Target 进入 Catalog/RAG；推荐先形成不受 Page Context 限制的推荐任务，再更新约束和确定 eligibility；比较先保留比较集合并解析产品身份，不能被当作单商品切换；任何路径都必须经过目标、证据与边界验证。

## 5. Conversation State

ConversationState 是会话当前派生状态的权威快照；原始消息历史单独保存。核心概念包括：

- **revision**：单调递增的状态版本，用于并发控制和幂等。
- **goal**：当前主要用户目标，例如发现、推荐、比较或商品问答。
- **constraints**：规范化后的有效、撤回、冲突或跳过约束。
- **waived_dimensions**：用户明确不希望继续澄清的维度。
- **pending_clarification**：上一轮等待回答的单个澄清问题及连续次数。
- **candidate_variants**：当前候选变体身份，不复制不稳定的动态事实。
- **recommendations**：最近一次正式或暂定推荐及其依据版本。
- **comparison_set**：当前比较的具体变体集合。
- **confirmed_product_context / confirmed_variant_context**：用户明确切换或确认后可供后续代词继承的 Conversation Context。
- **pending_target_switch**：等待用户确认的 Product / Variant 切换；确认前不覆盖已确认上下文。
- **catalog_version**：产生候选时所使用的目录版本。

设计约束：

- 状态更新通过 ConstraintPatch 和显式 action 完成，不让生成模型直接覆盖整个状态。
- Page Context 属于 TurnRequest；Turn Target 属于单轮解析结果。两者都不得仅因被观察或临时使用而静默覆盖已确认 Conversation Context。
- 动态 commerce 数据不长期固化为当前事实；回答前按策略刷新。
- MongoDB 保存 durable state 和历史 revision；Redis 只保存可重建缓存、锁和短期协调信息。
- revision 冲突必须返回可恢复语义，不可静默覆盖并发更新。

## 6. Core Contracts

本节只稳定跨模块必须共享的概念与语义。字段可在实现中细化，完整 wire schema 和文件结构应由真实代码及版本化接口维护。

### 6.1 TurnRequest

输入一轮对话所需的最小上下文：

- store_id
- conversation_id
- message_id
- user_text
- locale
- optional page product/variant context

要求：message_id 支持幂等；store_id 是所有后续读取与证据范围的强制边界。当前公共 TurnRequest wire schema 不包含 state revision，PageContext 也不包含 store_id；若目标切换实现需要客户端提交 expected revision，必须先提出版本化 Contract change 并通过 Human checkpoint。

### 6.2 Constraint and ConstraintPatch

Constraint 表示一个规范化条件：

- field
- operator
- value and unit
- hardness: HARD or SOFT
- status: ACTIVE, CONFLICTED, RETRACTED or WAIVED
- source turn and confidence/provenance

ConstraintPatch 表示本轮的增量动作：ADD、UPDATE、RETRACT、WAIVE 或 NO_CHANGE。应用 Patch 前必须完成单位、类型和冲突验证。

### 6.3 ConversationState

包含第 5 节定义的 revision、goal、constraints、waived dimensions、pending clarification、candidate variants、recommendations、comparison set、confirmed context、pending target switch 和 catalog version。状态必须可序列化、版本化和回放。

### 6.3.1 TargetResolution 与 TurnTarget

TargetResolution 记录本轮目标解析的输入、来源、结果和是否允许状态更新：

- `page_context`：请求携带的当前 Product 与 optional Variant；bundle 只能作为 Slice-local internal resolution detail 或未来版本化 public Contract proposal，当前 PageContext wire schema 不支持 bundle 字段。
- `explicit_references`：用户本轮显式指定的 Product / Variant 或多个比较对象。
- `confirmed_context`：ConversationState 中已确认、可被代词继承的对象。
- `turn_target`：`SINGLE_OBJECT`、`COMPARISON_SET`、`RECOMMENDATION_TASK`、`STORE_SUPPORT` 或 `NEEDS_CLARIFICATION` 之一。
- `resolution_source`：单对象目标使用 `EXPLICIT`、`CONFIRMED_CONTEXT`、`PAGE_CONTEXT` 或 `UNRESOLVED`；比较目标必须按 member 记录 provenance，不得用单值来源表达混合来源集合。
- `context_action`：`KEEP`、`SWITCH_CONFIRMED` 或 `AWAIT_CONFIRMATION`；只有 `SWITCH_CONFIRMED` 可产生 Conversation Context patch。

Turn Target 一经解析即作为本轮 RouteDecision、工具 scope、Answer、Product Card、Evidence、claim bindings 和 trace 的共同身份边界。Product / Variant 匹配必须限制在当前 `store_id`，零个或多于一个候选都进入澄清，不允许按目录顺序默认选择。

pending target switch 至少记录目标 Product / optional Variant identity、`created_by_message_id`、`created_at_revision`、`expected_revision`、来源 turn / triggering utterance category，以及 expiration / replacement / cancellation rule。`AWAIT_CONFIRMATION` 创建或替换 pending switch 时必须产生可回放的状态 diff，并单调增加 revision；重复 `message_id` 返回原结果，不再次增加 revision；同一 `message_id` 携带不同 payload 必须 fail closed。用户肯定确认在 `expected_revision` 匹配时转为 `SWITCH_CONFIRMED` 并恰好再增加一次 revision；否定、过期或取消清除 pending switch 并产生明确 diff；无关回复保持 pending switch 或按过期规则处理；再次提出新的切换按 replacement rule 替换旧 pending switch。

### 6.4 ProductRecord, VariantRecord and AttributeValue

- ProductRecord：商品身份、标题、共享描述、媒体和变体引用。
- VariantRecord：变体身份、选项、SKU、当前 commerce 引用、套装内容和覆盖属性。
- AttributeValue：值、单位、状态 KNOWN / UNKNOWN / NOT_APPLICABLE，以及来源和观测/版本信息。

要求：共享属性与变体覆盖必须有明确合并规则；最终资格和比较使用解析后的具体 VariantRecord。

### 6.5 ToolResult

统一 Shopify 与其他外部只读工具结果：

- status: SUCCESS, PARTIAL or ERROR
- typed data
- observed_at
- source
- error_code
- retryable

要求：超时、限流、鉴权、找不到和部分数据不得压缩为同一种空结果。

### 6.6 RouteDecision

- intent
- next action
- reason
- required capabilities
- Turn Target 与具体 product/variant scope 或 comparison set
- expected state update
- tool and time budget

要求：决策应可追踪；Router 输出动作计划，不输出最终候选真值。

### 6.7 Evidence

- evidence_id
- type: CATALOG, TOOL, DOCUMENT or DERIVED
- store_id
- optional product_id / variant_id
- source locator
- content or structured fact
- version / observed_at
- optional retrieval score

要求：DOCUMENT 证据必须能回到原始资料位置；DERIVED 必须引用其输入 Evidence；动态事实必须包含 observed_at。

### 6.8 AnswerEnvelope

- answer text
- resulting state revision
- constraint chips
- product cards
- optional comparison data
- citations / claim-evidence bindings
- follow-up or clarification
- fallback reason and actions
- freshness disclosure where relevant
- trace correlation ID

要求：组件可以渐进到达，但最终 Envelope 必须能被一致验证和回放。Answer、Card、Evidence 与 claim bindings 必须来自同一 Turn Target；Page Context 不能为跨产品回答补入规格、价格或库存。Client 应优先从既有 resolved object scope / Product Card 派生可见 target display；本规划不要求新增独立 public wire 字段。

## 7. Evidence and Fallback Semantics

### 7.1 Evidence precedence

同一事实存在多个来源时：

1. 当前 Shopify Tool 结果优先处理价格、库存和可售状态。
2. 规范化 Catalog 处理可确定的产品与变体属性。
3. 官方 Document Evidence 处理说明、操作步骤、FAQ 与政策语义。
4. Derived Evidence 只能表达由已引用事实计算出的结果，例如预算差额或重量比较。

来源冲突不得由语言模型静默融合；系统应选择权威层级、标记数据异常或 fallback。

### 7.2 Standard fallback result

Fallback 至少包含：稳定 reason code、用户可读说明、已知/未知范围、可执行下一步，以及是否可重试。V1 reason categories 与产品行为由 [PROJECT_SPEC.md](./PROJECT_SPEC.md) 定义。

## 8. Evaluation and Trace Design

评估分为四层：

- **Contract tests**：schema、商店隔离、revision、只读 allowlist、错误语义。
- **Module evals**：目标解析、临时/确认切换、约束 Patch、路由、硬过滤、变体选择、检索和证据绑定。
- **Journey evals**：用完整多轮脚本验证核心用户旅程和 fallback。
- **Operational checks**：延迟、错误率、重试、缓存一致性、敏感信息和成本。

Trace 的最小关联单位是一次 Turn。每次评估必须记录 Page Context、解析前 confirmed context、Turn Target、resolution source、context action 与状态 diff，以及所用数据集、模型/提示、目录版本、索引版本和 Decision 配置。质量门槛只在 [PROJECT_SPEC.md](./PROJECT_SPEC.md) 维护，避免指标在多个文档漂移。

## 9. Replaceable and Experimental Areas

以下内容不得被实现成不可替换的业务假设：

- Query Rewrite 的启用条件。
- 文档 Chunking 策略。
- 多商品检索候选分配。
- 是否启用通用或领域 Reranker。
- 是否需要 Fine-tuning。
- 软偏好 Recommendation Ranking 方法。
- Milvus 或其他向量/检索引擎。

其问题、当前选择、验证方法与结果由 [DECISIONS.md](./DECISIONS.md) 维护。Architecture 只要求这些能力通过稳定输入输出边界接入。

## 10. Initial Project Structure

以下 Tree 只表达当前 V1 的模块级边界，服务于 Vertical Slice 渐进开发；它不是完整或永久文件清单。

```text
消费级无人机智能导购Agent/
├── docs/
├── backend/
│   ├── api/
│   ├── conversation/
│   ├── agent/
│   ├── catalog/
│   ├── shopify/
│   ├── rag/
│   ├── evidence/
│   ├── evaluation/
│   └── common/
├── storefront/
├── tests/
│   ├── contract/
│   ├── integration/
│   └── e2e/
├── eval/
│   └── datasets/
└── scripts/
```

目录职责与边界：

- **docs/**：四个经批准的长期 Source of Truth；不保存临时开发进度。
- **backend/api/**：外部请求、身份、商店边界、幂等与响应传输；不放领域判断。
- **backend/conversation/**：ConversationState、ConstraintPatch 与轮次生命周期；不筛选商品。
- **backend/agent/**：有界路由与动作决策；不拥有目录真值或自由修改状态。
- **backend/catalog/**：规范化 Product/Variant 数据、单位及确定性约束/比较逻辑；不生成文档答案。
- **backend/shopify/**：Shopify 只读 adapter 与内部 Tool Contract 的实现边界；不做推荐排序。
- **backend/rag/**：授权文档摄取、索引与范围化检索；不回答实时 commerce 事实。
- **backend/evidence/**：证据校验、claim 绑定、回答组合和 fallback 表达；不绕过资格判断。
- **backend/evaluation/**：运行期 trace 与离线评估挂接；不成为会话权威状态。
- **backend/common/**：少量真正跨模块的共享类型、配置与基础协议；不得演变成无边界工具箱。
- **storefront/**：正式 Shopify 店面组件；消费后端 Contract，不复制后端领域逻辑。
- **tests/contract/**：跨模块与外部 adapter 的稳定语义测试。
- **tests/integration/**：若干真实模块协作的可重复验证，默认使用受控数据与替身。
- **tests/e2e/**：按 Vertical Slice 组织的完整用户旅程验证。
- **eval/datasets/**：版本化 golden cases、人工标注与数据说明；运行结果不应覆盖数据集。
- **scripts/**：可重复的开发、数据准备和评估入口；不承载核心业务逻辑。

当前不预建多租户、多 Agent、多品类、模型训练平台或未来任务管理目录。后续真实 Repository 是完整文件 Tree 的 Source of Truth。普通文件增删无需修改本节；只有模块职责或边界改变时才通过 Reconcile 更新 Architecture。

## 11. Decision Classification

- **Architecture Requirement**：为满足已批准 Product Behavior 而必须保持的技术性质，例如 Variant 级确定性硬过滤、版本化状态、证据归属和 Shopify 只读边界。
- **Current Design Choice**：当前有合理工程依据、作为 V1 默认落地的实现选择，但不是 Product Requirement，例如 FastAPI、MongoDB、Redis 与 TypeScript。
- **Provisional Design Choice**：可用于建立 baseline、但尚需实验或运维证据确认的候选，例如 Milvus。
- **Open Decision**：尚不能从现有证据定论，必须按 [DECISIONS.md](./DECISIONS.md) 中的验证方法选择，例如 Chunking、Reranker 与 Multi-product Retrieval。

这四类状态不得互换使用。开放选择即使在某个 Slice 中采用默认 baseline，也不会因此自动成为 Architecture Requirement。

## 12. Architecture Boundaries

- 本文件不维护完整项目文件树；文件组织以真实代码为准。
- 本文件不重复产品 Scope、Acceptance Criteria 或具体质量阈值。
- 本文件不把开放实验写成永久要求。
- 新 Evidence 可能促使 Architecture 或 Decisions 更新；涉及产品行为变化时必须同步审查 Project Spec。
- 完整文件 Tree 以真实 Repository 为准；本文件只在模块职责或核心 Contract 变化时更新。
