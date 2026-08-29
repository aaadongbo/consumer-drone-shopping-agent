# Slice 1 Implementation Plan — 商品页事实查询最小 E2E

> 状态：APPROVED / Authorized for T01
>
> Slice：01 — Product Facts
>
> 本文件只描述 Slice 1 的执行设计，不替代长期 Source of Truth。

## 1. Source of Truth 与 Readiness

本计划从以下已批准 Artifact 收敛而来：

- [PROJECT_SPEC.md](../../docs/PROJECT_SPEC.md)：Product Behavior、V1 Scope、Acceptance 与不可妥协门槛。
- [ARCHITECTURE.md](../../docs/ARCHITECTURE.md)：模块边界、Core Contracts、Evidence / Fallback / Trace 语义。
- [REFERENCE_ANALYSIS.md](../../docs/REFERENCE_ANALYSIS.md)：只复用有界 routing、typed tool、结构化引用与分层评估的经验。
- [DECISIONS.md](../../docs/DECISIONS.md)：尤其是 DEC-008、DEC-009、DEC-011；DEC-001～007 均不由本 Slice 提前决定。

规划前的只读检查结果：

| 检查 | 结果 |
|---|---|
| 工作目录 | `/Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent` |
| `git status --short` | 无输出，工作区干净 |
| `git log --oneline -3` | `cf26340 docs: establish V1 design baseline` |
| `git diff` | 无输出 |
| 基线 `cf26340` | 存在，类型为 `commit` |
| 四个核心 Artifact | 均存在且可读 |
| 核心 Artifact 相对基线的 diff | 无输出，无未经说明的修改 |
| 既有 Slice 1 Planning Artifact | 不存在 |

结论：Readiness Check 通过，可以创建本计划与 [tasks.md](./tasks.md)。完整重读未发现 Product Behavior、Architecture、Core Contract 或 Accepted Decision 之间会阻塞 Slice 1 的重大冲突。

## 2. Goal

建立一个可重复验证的商品页事实查询最小闭环：用户带着当前商品页上下文提出一个结构化商品事实问题，系统锁定正确的 Product / Variant，通过只读 Shopify Port 的确定性 fixture 获得事实，生成同一对象范围内的 Evidence，并返回可由版本化 schema 验证的 AnswerEnvelope 或明确 fallback；整轮由同一个 correlation ID 关联且 Shopify 写调用为零。

## 3. Scope

本 Slice 包含：

- 非正式店面的 Minimal Client / E2E Harness。
- 薄 Conversation API 与同步最终 AnswerEnvelope。
- `store_id + product_id + optional variant_id` 页面上下文验证。
- 最小 `PRODUCT_QA` / `OUT_OF_SCOPE` 路由。
- 可替换的 QuestionInterpreter Port；CI 使用 deterministic fake。
- Shopify read-only Port 的 Slice 1 子集与 deterministic fixture adapter。
- Product 共享事实和显式 Variant 事实查询。
- ToolResult 到 Evidence、claim binding、产品卡和结构化回答的组合。
- 规定范围内的标准 fallback。
- 最小、脱敏、Turn 级 trace。
- Static、Unit、Contract、Integration 与 E2E 分层验证。

## 4. Non-goals

本 Slice 不包含：

- 正式 Shopify Storefront Widget、正式流式协议或前端体验定型。
- 真实 Shopify 连接、凭据、生产配置或写操作。
- MongoDB、Redis、Milvus、RAG、文档摄取、Query Rewrite 或 Reranker。
- 完整 ConversationState、ConstraintPatch、revision history、状态合并、持久化或多轮恢复。
- 商品搜索、推荐、排序、比较、候选筛选或后续 Slice 行为。
- MCP adapter、开放式 Multi-Agent、完整 Agent Framework 或完整 Evaluation Platform。
- 真实模型作为 CI 依赖、fine-tuning 或模型供应商锁定。
- 全局 freshness TTL、缓存策略、SSE、WebSocket 或分块 HTTP 决策。
- 真实 Shopify / 真实模型 smoke 的执行；它们最多作为后续单独授权的非阻塞验证。

## 5. Walking Skeleton

```text
Minimal Client / E2E Harness
  -> Conversation API（校验版本化 TurnRequest）
  -> Page Context Resolver（store + product + optional variant）
  -> deterministic QuestionInterpreter + Minimal Router
  -> Shopify Read Port（Slice 1 allowlist）
  -> deterministic Fixture Adapter（记录只读调用）
  -> typed ToolResult
  -> Evidence Builder / Scope Validator
  -> Composer
  -> versioned AnswerEnvelope 或 Standard Fallback
  -> correlated Minimal Trace
```

最早的 Walking Skeleton 只需跑通“显式 Variant + 已知字段”的应用层 happy path；随后逐步加入 Product-only、失败语义、scope guard、薄 API 和完整 E2E matrix。不得为了这条链路建设未来模块。

## 6. Identity 与事实语义

### 6.1 Product / Variant identity

- Page Context 的强边界是 `store_id`、`product_id`，`variant_id` 可选。Slice 1 不新增独立 Identity 核心类型。
- 显式 `variant_id` 必须属于同一 `store_id + product_id`；不匹配按 Variant 不存在或 scope mismatch 处理，不尝试跨商品寻找同名变体。
- Product 共享事实必须是商品固有字段，或 fixture 明确标为对全部 Variant 共享的字段；不得通过观察某一个 Variant 推断共享事实。
- Variant-specific 字段只能在 Variant 明确时回答。Product-only 上下文不得静默选择默认、首个、最便宜或可售 Variant。
- Product 属性与 Variant 覆盖的解析规则必须显式且确定：查询 Variant 时使用该 Variant 的已知覆盖；没有覆盖时只能继承被声明为 Product 共享的值。
- Product Card 在 Slice 1 AnswerEnvelope 中可省略，缺少 Card 本身不构成失败。若 Card 存在，其 `store_id/product_id/optional variant_id` 必须与 Answer resolved scope、Evidence 和 claim binding 一致；不一致时 fail closed。正式 Widget 是否永久展示 Card deferred。

### 6.2 Dynamic facts

- `price`、`inventory`、`availability` 只能来自本轮 Shopify Read ToolResult，不从文档、模型、旧 trace 或隐藏 fixture 快照外推。
- 动态事实的 ToolResult、Evidence 和最终 freshness disclosure 均保留 `observed_at` 或可一一映射的等价时间。
- Slice 1 不设全局 freshness TTL；`observed_at` 表示本次 read adapter 的观测时间，不等于永久“实时”。
- Tool 失败、partial 或动态事实缺少观测时间时，不输出确定动态事实；返回对应 fallback。

### 6.3 UNKNOWN

- `UNKNOWN` 表示授权数据不能确认该字段；不等于 `false`、`0`、空字符串、`NOT_APPLICABLE` 或“不支持”。
- 无可用 Evidence 的字段不得由模型常识补全。
- Slice 1 的保守基线是：用户请求的单一事实为 UNKNOWN / missing 时返回明确 fallback，而非生成事实结论。

## 7. Converged Acceptance

下表是 Slice 1 的 PASS / FAIL 判据，不重新定义完整 V1 Acceptance。

| ID | Acceptance | PASS 条件 | FAIL 示例 | 推荐验证层级 |
|---|---|---|---|---|
| A-01 | 显式 Variant 身份一致 | Answer scope、Evidence、claim binding 携带同一 `store_id/product_id/variant_id`；Product Card 可省略，若存在也必须一致 | 回答 Variant A 的价格但存在的卡片或证据指向 Variant B；缺少 Card 不算失败 | Contract + Integration + E2E |
| A-02 | Product-only 共享事实 | 没有 `variant_id` 时，仅回答 fixture 明确声明的 Product 共享事实 | 从首个 Variant 取飞行时间并说成该 Product 的共同值 | Unit + E2E |
| A-03 | Variant ambiguity | Product-only 请求 Variant-specific 字段时返回 `VARIANT_REQUIRED`，说明需要选择 Variant | 静默选择默认 Variant | Unit + E2E |
| A-04 | 不跨 Variant 混合 | 一个结果只从解析后的单一 Variant 取 price / inventory / bundle / attribute | Variant A 的价格拼 Variant B 的库存 | Unit + Integration |
| A-05 | Evidence scope guard | Composer 只接受与回答对象相同 store/product/variant 范围的 Evidence；失败时不返回事实 ANSWER，trace 保留具体 internal diagnostic，对外返回统一 consistency fallback | 错商品 Evidence 仍生成肯定回答，或把内部对象细节直接返回客户端 | Unit + Contract + E2E |
| A-06 | 动态事实来源 | price / inventory / availability 来自当前 read call 的 ToolResult | 从静态描述或模型输出价格 | Contract + Integration |
| A-07 | 动态事实新鲜度 | 动态 ToolResult、Evidence 与 Answer freshness 可追踪到 `observed_at`；缺失时 fail closed，内部诊断可定位且公开响应不扩张 reason-code taxonomy | 返回当前价格但无观测时间，或对外泄漏内部校验细节 | Contract + E2E |
| A-08 | Tool 失败不冒充实时 | timeout / rate limit / auth / partial 均不以 fixture、缓存或旧数据补写实时结论 | timeout 后仍声称“当前有货” | Integration + E2E |
| A-09 | 结构化 Evidence | KNOWN 事实生成带 field locator、正确对象范围和来源的 Evidence | 只有自然语言引用、不能定位字段 | Contract + Unit |
| A-10 | UNKNOWN 忠实表达 | UNKNOWN / missing 返回无法确认语义，不转为 false、0 或不支持 | 未知避障能力回答“不支持” | Unit + E2E |
| A-11 | 无 Evidence 不作事实结论 | 每个关键商品事实 claim 至少绑定一个通过 scope 校验的 Evidence | 生成了参数但 bindings 为空 | Contract + Unit |
| A-12 | Fallback 可判别、可行动 | 第 8.8 节公开失败类别都有稳定 public reason code、用户说明、retryable 和至少一个 next action；内部一致性失败统一公开为 `INTERNAL_CONSISTENCY_ERROR` | 所有失败都是 `ERROR`/空回答，或把 internal diagnostic 暴露为 public reason code | Contract + E2E |
| A-13 | 版本化 wire contract 与 transport rejection | 有效 TurnRequest 和最终 AnswerEnvelope（含业务 fallback）分别通过同一公共版本化 contract set；无效 TurnRequest 在 transport boundary 被稳定拒绝且不产生 AnswerEnvelope | 无效 TurnRequest 进入 application，或被包装成业务 fallback | Contract + E2E |
| A-14 | Client/API contract 一致 | Harness 直接使用公共 wire schema 构造/验证 payload，不能绕过 validation；transport validation response 稳定且不泄漏内部异常 | Harness 手工拼装特殊 payload 绕过 schema，或 invalid input 触发 Interpreter/Shopify | Contract + E2E |
| A-15 | 完整 correlation | 同一 correlation ID 关联 request、page context、route、tool call/result、Evidence、最终 answer/fallback | 工具结果无法追溯到请求 | Integration + E2E |
| A-16 | Trace 安全 | token、secret、credential、Authorization header 和敏感配置既不记录值，也不整包 dump | trace 保存 Shopify access token | Unit + Operational check |
| A-17 | Shopify 只读 | Port 无写方法，allowlist 仅开放 Slice 1 read operations，所有测试的 write-call count 为 0 | 暴露 cart/order/product update 或未知 operation 可透传 | Static + Contract + E2E |
| A-18 | 范围外请求 | 非 Product Fact Query 返回 `OUT_OF_SCOPE` 和可执行引导，不调用 Shopify | 问推荐时进入自由 Agent 循环或伪造推荐 | Unit + E2E |

## 8. Minimal Contracts

以下定义是 Slice 1 跨模块共享的最小语义；实现时由真实代码和版本化 wire schema 固化字段名、必填性与序列化规则。

### 8.1 TurnRequest

最小字段：

- `schema_version`
- `store_id`
- `conversation`: `conversation_id`, `message_id`
- `user_text`
- `locale`
- `page_context`: `product_id`, optional `variant_id`

`message_id` 提供单轮幂等引用语义，但 Slice 1 不建设持久幂等存储。`state_revision` 当前不需要，明确 deferred；若 wire compatibility 需要占位，只能是 optional 且不得触发状态持久化或 revision 逻辑。

无效 TurnRequest 在 transport boundary 被拒绝，不进入 application service，不调用 QuestionInterpreter 或 Shopify adapter，也不生成业务 AnswerEnvelope fallback。Transport validation response 必须稳定、可测试且不泄漏内部异常；具体 HTTP status 与最小 validation body 由 T02/T08 基于实现记录，不建设完整 API Error Framework。

### 8.2 ProductRecord / VariantRecord

`ProductRecord` 最小字段：`store_id`, `product_id`, display title, 显式 Product-shared `attributes`，以及 Variant references（只含身份，不复制 Variant 值）。

`VariantRecord` 最小字段：`store_id`, `product_id`, `variant_id`, display label/options, Variant-specific `attributes`。动态 commerce 字段通过本轮 read ToolResult 提供，不固化为长期真值。

无需新增独立 `ProductIdentity` / `VariantIdentity` 类型；三元 scope 在共享 Contract 中保持一致即可。

### 8.3 AttributeValue

最小字段：

- `status`: `KNOWN | UNKNOWN | NOT_APPLICABLE`
- `value`（仅 `KNOWN` 时存在）
- optional `unit`
- `source_ref` 或可映射到 Evidence locator 的来源
- optional `observed_at`；动态字段为必填

验证规则禁止 UNKNOWN 携带假值，也禁止 KNOWN 缺少值。`NOT_APPLICABLE` 必须由明确 schema/商家数据表达，不从缺失值推导。

### 8.4 Shopify Read Port 与 ToolResult

Slice 1 allowlist 仅使用 Architecture 已定义能力的必要子集：

- `get_products`
- `get_variants`
- `refresh_commerce_state`（仅动态事实请求时）

不需要 `search_products`，也不存在任何 write method。Adapter 不接收任意 operation string 后再透传。

`ToolResult` 最小字段：

- `status`: `SUCCESS | PARTIAL | ERROR`
- typed `data`
- `source`
- `observed_at`
- optional `error_code`
- `retryable`
- PARTIAL 时的明确 `missing_fields` 或等价缺口

Timeout、rate limit、authorization、Product not found、Variant not found 和 partial 必须保持不同语义，不能压缩为 `null data`。

### 8.5 Minimal RouteDecision / QuestionInterpreter

`RouteDecision` 最小字段：

- `intent`: `PRODUCT_QA | OUT_OF_SCOPE`
- `action`: read product fact、read variant fact、request variant clarification 或 return fallback 中的一项
- normalized `requested_field`
- declared field scope：Product-shared、Variant-specific 或 Dynamic Variant fact
- resolved product/variant scope
- human-readable/traceable `reason`

自然语言到 `requested_field + field scope` 的解释若需要模型能力，通过可替换 `QuestionInterpreter` Port 完成。CI 使用 deterministic fake；真实模型是 optional smoke。Interpreter 不产生商品事实、不覆盖 ToolResult、不改变 scope 校验。

### 8.6 Evidence

最小字段：

- `evidence_id`
- `type`: Slice 1 使用 `TOOL`（若实现把规范化共享属性标为 `CATALOG`，也必须来自同一 fixture read 记录）
- `store_id`, `product_id`, optional `variant_id`
- `field_locator`
- typed fact / AttributeValue
- `source`
- optional `observed_at`；动态事实必填

`evidence_id` 由系统生成且在同一 Envelope 内唯一。Evidence 不携带凭据或原始请求 header。

### 8.7 AnswerEnvelope

最小 wire 语义：

- `schema_version`
- `outcome`: `ANSWER | FALLBACK`
- `conversation` message reference
- `trace_correlation_id`
- resolved object scope
- user-readable `text`
- zero or more typed facts/claims
- optional minimal Product Card；省略合法，若存在则明确 identity 并通过与 resolved scope、Evidence、bindings 相同的 identity gate
- Evidence collection
- claim-to-evidence bindings
- optional freshness disclosure
- outcome 为 FALLBACK 时的 Standard Fallback

成功 Answer 的每个关键事实 claim 必须绑定 Evidence。同步 Envelope 是 Slice 1 baseline；不定义 stream event。

### 8.8 Standard Fallback

最小字段：`reason_code`, `message`, `retryable`, `next_actions`，以及可安全披露的 resolved scope。Slice 1 稳定 reason codes：

| Reason code | 场景 | retryable baseline | 至少一个 next action |
|---|---|---:|---|
| `PRODUCT_NOT_FOUND` | 当前 store 内 Product 不存在 | false | 返回商品页或重新选择商品 |
| `VARIANT_NOT_FOUND` | Variant 不存在或不属于 Product | false | 重新选择有效 Variant |
| `VARIANT_REQUIRED` | Variant-specific 请求但 Variant 不明确 | false | 选择/提供 Variant |
| `FACT_UNKNOWN_OR_MISSING` | 请求字段在授权数据中 UNKNOWN / missing | false | 查看其他已知规格或联系商家 |
| `TOOL_TIMEOUT` | read 超时 | true | 重试 |
| `TOOL_RATE_LIMITED` | read 被限流 | true | 稍后重试 |
| `TOOL_UNAUTHORIZED` | read 鉴权失败 | false | 联系支持/检查商店连接 |
| `TOOL_PARTIAL_RESULT` | 请求事实未包含在 partial result | true | 重试或询问可确认字段 |
| `INTERNAL_CONSISTENCY_ERROR` | scope、binding、output identity 或动态 freshness 完整性校验失败 | false | 停止展示该结论并联系支持 |
| `OUT_OF_SCOPE` | 请求不是当前 Product Fact Query | false | 引导到支持范围或人工渠道 |

`retryable` 表示以相同意图重试是否可能成功，不代表自动无限重试。Slice 1 不实现重试编排。

`INTERNAL_CONSISTENCY_ERROR` 是上述完整性失败唯一的公开 reason code，baseline 为 `retryable=false`，避免客户端自动重复一个可能确定性失败的请求。公开 message 保持安全、简洁、可行动，不包含对象值、stack、schema 或调试信息。内部 trace 必须保留具体 diagnostic code：

- `EVIDENCE_SCOPE_MISMATCH`
- `OUTPUT_SCOPE_MISMATCH`
- `DYNAMIC_FACT_FRESHNESS_MISSING`

这些 internal diagnostics 用于 negative tests、日志和诊断，不能被静默吞掉，也不是 public wire fallback enum。动态事实缺少 `observed_at` 同样映射到公开 `INTERNAL_CONSISTENCY_ERROR`，不新增公开 reason code。

### 8.9 Minimal Trace

最小结构化事件共享：`schema_version`, `correlation_id`, `event_type`, `occurred_at` 与安全的对象/结果摘要。必须能关联以下事件：

- TurnRequest accepted/rejected
- Page Context resolved/rejected
- RouteDecision
- Shopify read call（operation 名称、scope，不含认证信息）
- ToolResult（status/error/observed_at 摘要）
- Evidence accepted/rejected
- AnswerEnvelope 或 fallback produced

Trace 是内存或测试 sink 即可，不是 ConversationState 或 durable store。采用字段 allowlist 和敏感键/值清理；禁止 header、token、secret、credential、环境配置和未经筛选的 request/response dump。

## 9. Module Responsibilities

| Slice-local component | 负责 | 不负责 |
|---|---|---|
| Minimal Client / E2E Harness | 按公共 schema 发 TurnRequest、解析最终 Envelope、驱动案例 | 正式 Widget、领域判断、独立 contract |
| Conversation API | 在 transport boundary 完成 wire validation；只有有效请求才建立 correlation、协调 application 并返回同步 Envelope | 把 invalid TurnRequest 包装成业务 fallback、调用 Interpreter/Shopify、推荐、RAG、完整 state、业务事实生成 |
| Page Context Resolver | 校验 store/product/variant 组合，输出明确 scope | 搜索替代商品、默认选 Variant |
| QuestionInterpreter + Router | 把问题限制到允许字段与 PRODUCT_QA / OUT_OF_SCOPE 动作 | 产生事实、覆盖 tool/evidence |
| Shopify Read Port | typed read capabilities、错误分类、allowlist | 写能力、自然语言、推荐 |
| Fixture Adapter | 确定性数据、失败注入、观测时间、调用账本 | 模拟真实 Shopify 完整行为、网络 |
| Evidence Builder / Validator | ToolResult 转 Evidence、校验 scope/freshness/UNKNOWN | 用模型补事实、静默修正错 scope |
| Composer | 只用通过验证的 Evidence 生成 Envelope/Card/bindings 或 fallback | 修改事实、选择其他 Variant、放宽 gate |
| Trace Sink | 关联最小事件并验证脱敏 | 权威状态、完整观测平台 |

## 10. Fixture / Port Strategy

- Fixture 数据必须至少包含：两个 Product、同一 Product 下两个差异明显的 Variant、Product-shared known 字段、Variant-specific known/UNKNOWN 字段，以及互相不同的价格/库存/套装值，以便暴露跨 Variant 拼接。
- 每个 fixture record 固定 `store_id/product_id/variant_id` 和来源 locator；测试可注入固定 `observed_at`，避免 wall-clock 不确定性。
- Adapter 支持确定性注入 `SUCCESS/PARTIAL/ERROR` 以及 timeout、rate limit、authorization 和 not-found 分类。
- Adapter 维护 call ledger：operation、safe scope、read/write classification。Contract/E2E 断言 allowlist 外调用被拒绝且 write-call count 为 0。
- Fixture 是 CI 的测试 double，不得在用户文案中描述成真实 Shopify 当前状态；测试只验证“当前 ToolResult 优先”的语义。
- Port 与 fixture 都使用内部 typed contract，遵守 DEC-011，不创建 MCP schema。

## 11. Verification Strategy

### 11.1 分层 Gate

- **Change Unit**：Static + 与改动直接相关的 Unit / Contract；只验证本 Task 引入的边界。
- **Walking Skeleton**：Integration；使用 deterministic interpreter 和 Shopify fixture 跑通应用层 happy path，然后补失败路径。
- **Slice Completion**：全部 completion-gate E2E、公共 wire schema、diff review、只读/隐私检查与 Completion Evidence。
- **Optional Live Smoke**：真实 Shopify 或真实模型；需要独立授权，不能成为 CI 或 Slice 1 完成的唯一依赖。

### 11.2 Verification Matrix

| # | 场景 | Test level | Fixture / input | Expected result | Acceptance | Completion gate |
|---:|---|---|---|---|---|:---:|
| 1 | 指定 Variant，字段已知 | Integration + E2E | Product P1 / Variant V1，请求已知 Variant 属性；覆盖 Card omitted 与 Card present | ANSWER；Card 省略仍合法；若存在，scope/card/evidence/binding 均为 P1/V1 | A-01, A-04, A-09, A-11 | 是 |
| 2 | 只有 Product，共享字段已知 | Unit + E2E | P1，无 Variant，请求 shared field | ANSWER；Evidence 为 Product scope，不虚构 Variant | A-02, A-09 | 是 |
| 3 | 只有 Product，请求 Variant-specific | Unit + E2E | P1，无 Variant，请求 price/bundle 等 | `VARIANT_REQUIRED`，不调用 Variant 事实组合 | A-03, A-12 | 是 |
| 4 | Product 不存在 | Integration + E2E | missing product ID | `PRODUCT_NOT_FOUND` | A-12 | 是 |
| 5 | Variant 不存在 | Integration + E2E | P1 + missing/foreign Variant | `VARIANT_NOT_FOUND`，不跨 Product 回退 | A-01, A-12 | 是 |
| 6 | 字段 UNKNOWN | Unit + E2E | V2 的 requested AttributeValue=UNKNOWN | `FACT_UNKNOWN_OR_MISSING`；文本不含“不支持”式确定结论 | A-10, A-11, A-12 | 是 |
| 7 | Tool timeout | Integration + E2E | timeout injection | `TOOL_TIMEOUT`, retryable=true，无事实 claim | A-08, A-12 | 是 |
| 8 | Tool rate limit | Integration + E2E | rate-limit injection | `TOOL_RATE_LIMITED`, retryable=true | A-08, A-12 | 是 |
| 9 | Tool authorization failure | Integration + E2E | auth failure injection | `TOOL_UNAUTHORIZED`, retryable=false | A-08, A-12 | 是 |
| 10 | Tool partial result | Integration + E2E | PARTIAL 且缺 requested field | `TOOL_PARTIAL_RESULT`，不补写缺失事实 | A-08, A-12 | 是 |
| 11 | Evidence product scope 错误 | Unit + E2E | Answer P1，Evidence P2 | 不返回事实 ANSWER；public `INTERNAL_CONSISTENCY_ERROR`；trace `EVIDENCE_SCOPE_MISMATCH` | A-05, A-11, A-12 | 是 |
| 12 | Evidence variant scope 错误 | Unit + E2E | Answer V1，Evidence V2 | 不返回事实 ANSWER；public `INTERNAL_CONSISTENCY_ERROR`；trace `EVIDENCE_SCOPE_MISMATCH` | A-01, A-05, A-12 | 是 |
| 13 | 存在的 Product Card 与 Answer Variant 不一致 | Unit + Contract | Answer V1，Card V2 | 不返回事实 ANSWER；public `INTERNAL_CONSISTENCY_ERROR`；trace `OUTPUT_SCOPE_MISMATCH`；无 Card 的合法 Envelope 不失败 | A-01, A-04, A-12 | 是 |
| 14 | 动态事实缺少 observed_at | Contract + E2E | SUCCESS price，observed_at missing | 无当前价格结论；public `INTERNAL_CONSISTENCY_ERROR`；trace `DYNAMIC_FACT_FRESHNESS_MISSING` | A-07, A-08, A-12 | 是 |
| 15 | 请求超出 Product Fact Query | Unit + E2E | 推荐/订单/法规权威结论等输入 | `OUT_OF_SCOPE`，Shopify call count=0 | A-18 | 是 |
| 16 | 完整 Trace 关联 | Integration + E2E | 任一成功及任一 fallback turn | 必需事件共享同一 correlation ID | A-15 | 是 |
| 17 | 敏感信息不进入 Trace | Unit + Operational | 注入 token/header/secret-shaped input | trace sink 中无敏感值、无原始 header dump | A-16 | 是 |
| 18 | Shopify 写调用为 0 | Static + Contract + E2E | 全 suite + unknown/write operation probes | Port 无写 surface；probe 被拒绝；ledger write count=0 | A-17 | 是 |
| 19 | 无效 wire input 停在 transport boundary | Contract + E2E | 缺必填字段、非法 schema version/type 的 TurnRequest | 稳定且无内部异常泄漏的 transport rejection；无 AnswerEnvelope；application/Interpreter/Shopify call count=0 | A-13, A-14 | 是 |

所有 19 个场景均为 Slice completion gate。真实 Shopify / 真实模型 smoke 不属于 completion gate。

## 12. Assumptions 与 Slice-local Open Decisions

### 12.1 当前 assumptions

- 首个实现遵循 Architecture 的 Python/FastAPI current design choice，但具体包布局由 Task 1 根据当时 repository 和最小依赖决定；语言不是产品 Requirement。
- 直接服务该 baseline 的最小 Python 项目/test runner、static/type/format 工具、FastAPI 配套 schema validation、最小 HTTP test client、deterministic fixture 与测试辅助库，不触发 Human Escalation。依赖必须最小、版本明确、可替换、实际使用且不自动引入大型框架；具体库版本在 T01/T02 执行时基于当时环境确认并记录，本 Planning 不锁定。
- API 可同步返回最终 AnswerEnvelope；正式渐进/流式 UX deferred。
- `state_revision` deferred；ConversationRef 只稳定 `conversation_id/message_id`。
- 动态字段视为 Variant-specific；没有 Variant 时请求 price/inventory/availability 返回 `VARIANT_REQUIRED`。
- CI 的 deterministic interpreter 只识别测试字段词表和明确 out-of-scope 样例，不声称覆盖完整自然语言。
- Partial result 缺 requested field 时采用保守 fallback；不实现混合“部分回答 + 警告”的复杂 envelope。
- Trace 使用进程内/测试 sink，保存最小安全事件；durability deferred。
- 不设 freshness TTL；只验证本次 read 的 `observed_at` 传播。

### 12.2 Slice-local open decisions

以下选择会影响局部实现，但当前不阻塞计划，也不需要更新 DECISIONS.md：

1. 公共 wire schema 使用何种直接配套的 Python schema validation 库及版本声明形式，由 Task 1/2 在允许的最小依赖边界内决定。
2. Minimal Client 采用进程内 test client 还是极薄 CLI，由最小 E2E 成本决定；两者都不是正式 Widget。
3. 静态结构化事实的 Evidence 类型采用 TOOL 还是 CATALOG；来源仍须是受控 Shopify fixture record，不能引入 Catalog Engine。

若上述选择演变成跨 Slice 核心 Contract 或主要依赖，必须升级为 Human Escalation，而非在实现中静默固定。

## 13. Human Escalation Conditions

出现以下任一情况立即停止受影响工作，输出 Discovery / Evidence / Impact / Options / Recommendation / Blocked work，并请求 Human Decision：

- 必须改变 Slice 1 Product Behavior 或本计划 Acceptance 才能继续。
- 必须改变 Product / Variant 核心身份语义。
- 必须改变 ToolResult、Evidence、AnswerEnvelope 或 Accepted Decision 的核心语义。
- 需要数据库或 durable state、Redis、消息系统、任务队列、RAG、向量数据库、Agent Framework、外部托管基础设施或 observability platform。
- 需要影响多个 Slice 的主要生产依赖、改变 Architecture Boundary 的依赖，或使真实外部服务成为 CI 运行前提。第 12.1 节列出的 Python/FastAPI Slice 1 最小配套依赖不属于本项，但仍须遵守最小、明确版本、可替换和只引入实际使用依赖的约束。
- 真实 Shopify 数据模型明显违背 Architecture 假设。
- Scope 扩大到推荐、比较、多轮、RAG、正式 Widget 或 Slice 2～7。
- 需要把 MCP 变成内部核心 Contract、开放式 Multi-Agent 或 Shopify 写操作。
- 需要降低事实一致性、Evidence、安全、隐私、只读或动态新鲜度 Gate。
- 需要把真实 Shopify / 真实模型变为 CI 唯一依赖。
- 四个核心 Artifact 不能同时满足。

普通文件组织、私有函数、fixture 形状、局部测试数据和不改变共享语义的类型细化由执行 Agent 自主处理。

## 14. Reconcile Rules

Discovery 先分类为 Implementation、Task、Slice Plan、Architecture、Product Spec 或 Decision：

- 只影响 Implementation / Task：更新实现与 [tasks.md](./tasks.md) 的执行记录。
- 影响本 Slice 排序、假设或局部方案：更新本计划与 tasks，并记录原因。
- 影响 Product Behavior、Architecture Boundary、核心跨模块 Contract 或 Accepted Decision：停止，不自行修改核心 Artifact，按第 13 节升级。
- 确定性、重复性要求优先固化到测试、schema、allowlist 或 CI，而非创建 Skill。
- 本 Slice 不创建 `.agent/STATE.md` 或第三套状态文件；Git history、当前 diff 与 tasks.md 共同记录执行状态。

## 15. Completion Evidence

Slice 1 只有在以下证据齐备后才可标为完成：

- tasks.md 中所有 completion task 为 DONE，且每项记录实际执行命令、退出结果和对应测试/日志位置。
- Verification Matrix 19 个 completion gates 全部 PASS。
- 公共 TurnRequest / AnswerEnvelope wire schema 的 contract test 结果。
- 指定 Variant happy path 与主要 fallback 的 deterministic E2E 结果。
- Internal diagnostic 到公开 `INTERNAL_CONSISTENCY_ERROR` 的映射、公开响应不泄漏内部细节，以及 invalid TurnRequest transport rejection 的 negative test 结果。
- Tool call ledger 证明全套测试 Shopify write-call count = 0。
- Trace correlation 与敏感信息 negative test 结果。
- 最终 `git diff` review：无 RAG、state store、正式 Widget、MCP、推荐/比较或其他后续 Slice 实现。
- 代码、fixture、schema 和文档 diff 可由单一 Slice 解释；核心 Artifact 若无 Human Decision 不得改动。
- Optional live smoke 若未运行，明确记录为未运行且不阻塞完成；若运行，记录独立授权与结果，不把凭据写入仓库。

## 16. Implementation Entry Condition

Human Final Approval 已获得，Slice 1 已具备进入新的 Implementation Session 的条件，并授权从 **T01 — Bootstrap 最小执行与测试 Harness** 开始。当前 Planning Session 只确认批准状态并建立本地 Planning baseline，仍不得执行 T01。

## 17. Approval Record

- Decision：APPROVED
- Authorized starting task：T01 — Bootstrap 最小执行与测试 Harness
- Approval scope：[plan.md](./plan.md) 与 [tasks.md](./tasks.md)
- Scope boundary：本次批准不授权 Slice 2～7
