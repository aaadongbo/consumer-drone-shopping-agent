# Slice 7 Planning — Fallback, Trace and Storefront Closure

> 状态：APPROVED PLANNING / NON-EXECUTABLE
>
> Human 已接受本规划的目标、Scope、Acceptance、预算和任务表。它仍不授权 Implementation、snapshot、commit、push 或真实外部服务配置；进入实现前仍需建立 planning baseline 并激活 S07 Workflow Policy。

## 1. Baseline and boundary

- Current main baseline：`3921fd20eab03737295d6072f22aca1c731a3cf9`，Slice 6 已集成。
- Slice 1～6：已完成；其公共 Contract、只读 Shopify 边界、Evidence Gate、Target Resolution 和 Recommendation flow 视为输入。
- 当前没有正式 Slice 7 Task、Workflow Policy 或实现授权。
- 本 Slice 不回写前六个 Slice 的业务语义；发现核心行为或 Contract 冲突时停止并请求 Human Decision。

## 2. Goal

把现有 Conversation API、Product QA、Product RAG、Comparison 和 Recommendation 能力接入一个最小正式店面闭环：用户能看到当前回答对象、答案或可行动 fallback；每个 Turn 的输入、状态、路由、工具、候选、Evidence 和输出可通过安全 trace 关联；发布前可运行一套可重复的 E2E 与质量门禁。

## 3. Scope

In scope:

- 复用现有 `TurnRequest`、`AnswerEnvelope` 和 `Fallback`，建立内部 storefront view-model 与安全渲染边界。
- 展示当前回答对象、Product/Variant scope、UNKNOWN/不可用和下一步动作；不让客户端自行拼接事实。
- 展示当前有效约束与 pending clarification；用户可通过正式服务端状态路径新增、修改、撤回或明确跳过约束，客户端不自行成为状态权威。
- 将现有 trace 事件汇总为按 Turn 的最小关联记录，并在进入输出、日志或测试 sink 前脱敏。
- 最小 storefront shell：发送问题、展示 loading、ANSWER/FALLBACK、当前对象和重试/澄清动作。
- API 到 storefront 的确定性 E2E 回放，覆盖商品页问答、跨产品显式目标、比较、推荐、RAG 缺证和失败路径。
- 发布前的完整测试、质量指标 baseline、失败处置记录和 Slice completion evidence。

Out of scope:

- 改变现有公共 wire Contract、Target Resolution 优先级、Evidence Gate 或 Shopify Read Port。
- 真实 Shopify、真实模型、开放网络、客服/售后外部系统、支付、购物车、订单或客户数据。
- 生产级 observability 平台、数据库/队列、长期用户画像、多租户、A/B 平台或复杂前端框架。
- 新的 RAG 引擎、reranker、fine-tuning、学习排序、自动工具循环或 Shopify write。
- 强制引入新的运行时依赖；如 storefront 技术栈或浏览器 CI 需要主要依赖，先停 Human checkpoint。

## 4. Product behavior

- 商品页上下文继续作为默认对象；Answer 必须显示实际 Turn Target 的 Product/Variant scope。
- 正式组件必须展示当前有效约束与当前澄清状态；用户新增、修改、撤回或跳过约束后，下一轮只能以服务端确认的最新状态继续。每轮最多一个澄清问题、连续最多两轮的既有 V1 规则不得由客户端绕过。
- Fallback 必须可读、可行动且不泄漏内部诊断；重试、澄清、切换和联系支持等动作只能来自服务端结果。
- 当前对象、Answer、Card（若存在）、Evidence 和 trace 的 identity 必须一致；客户端不得把旧回答渲染成当前事实。
- Trace 只用于关联和审计，不成为会话状态权威；敏感信息、凭据、完整请求 payload 和异常 stack 不得进入 trace。
- 浏览器/客户端失败与业务 fallback 分层展示；HTTP transport rejection 不伪装成业务答案。

## 5. Minimal contracts

以下是 Slice-local/internal proposal，不改变现有 public wire schema：

- `StorefrontTurnView`：客户端本地、由既有 public response 与本地 UI 状态派生的 correlation id、resolved target display、answer/fallback envelope、render status；它不是新的 API DTO。
- `ConstraintPresentationState`：客户端展示的已确认有效约束、pending clarification 和用户动作状态；其权威结果只能来自既有服务端状态/响应。若现有 API 无法提供或提交所需数据，必须提出版本化 public Contract proposal 并停在 Human checkpoint。
- `FallbackView`：public reason、message、retryable、next actions；不暴露内部 diagnostic code。
- `TraceTurnRecord`：correlation id、request/context summary、route、tool summaries、candidate/evidence IDs、output kind、redaction result。
- `QualityRunRecord`：dataset/matrix version、command result、pass/fail、latency/error summary、known limits。

若实现需要在 public `TurnRequest`、`AnswerEnvelope` 或 Widget payload 增加字段，必须在对应 Task 形成版本化 Contract proposal 并停在 Human checkpoint。

## 6. Provisional budgets and quality gates

复用前序 Turn 预算：`max_action_rounds=2 total`、`max_tool_calls=2`、`turn_deadline_ms=8000`、`max_retrieval_tokens=4000`、`max_model_tokens=1200`。Storefront 只增加展示侧软预算：单次渲染不自动重复提交，客户端重试由用户动作触发。

以下为待真实环境验证的 provisional baseline，不在本规划中假装已达标：

- API/应用现有单元、Contract、集成测试必须通过。
- Storefront E2E 覆盖核心成功、fallback、transport rejection 和敏感信息脱敏。
- 记录测试版本、运行命令、实际 exit code、已知限制和处置结论；性能阈值由 T05 实验后再决定是否调整。

## 7. Acceptance

| ID | Acceptance | PASS condition |
|---|---|---|
| S7-A01 | Existing contract reuse | Storefront 请求和响应复用现有公共 schema；无隐式旁路 payload。 |
| S7-A02 | Constraint and clarification view | 当前有效约束、冲突和 pending clarification 可见；新增、修改、撤回、跳过会通过服务端确认反映在下一轮；每轮最多一个、连续最多两轮澄清。若当前 public Contract 无法承载，先停版本化 Contract checkpoint。 |
| S7-A03 | Target display | Answer/视图显示实际 Product/Variant scope；不显示过期或混合对象。 |
| S7-A04 | Fallback rendering | 失败、未知、不可用和 transport rejection 分层且可行动；不泄漏内部诊断。 |
| S7-A05 | No client facts or state authority | 客户端不自行计算、拼接或覆盖商品事实、Evidence、推荐理由或约束权威状态。 |
| S7-A06 | Trace correlation | request、state、route、tool、candidate、Evidence、output 可由同一 correlation id 关联。 |
| S7-A07 | Trace redaction | trace/output 不含 token、header、credential、完整 payload、异常 stack 或敏感源文本。 |
| S7-A08 | Retry semantics | 只有服务端标记 retryable 且用户触发时才可重试；不自动形成工具循环。 |
| S7-A09 | Core journeys | 商品问答、RAG、比较、推荐和约束多轮澄清在正式组件中可回放。 |
| S7-A10 | Failure journeys | 无匹配、缺证、动态失败、范围冲突、超时和 invalid input 均有稳定展示。 |
| S7-A11 | Read-only safety | 所有 Shopify 路径 write-call count 为 0；无开放网络或外部客服调用。 |
| S7-A12 | Quality evidence | full suite、E2E matrix、静态检查和质量 baseline 有实际命令结果与处置记录；指标/Spec 调整由 Human 决定。 |
| S7-A13 | No premature expansion | 未引入主要依赖、公共 Contract、架构边界或 Slice 8+ 能力。 |

## 8. Verification matrix

| Matrix | Scenario | Expected |
|---:|---|---|
| 1 | 商品页 Variant 商品事实 | 当前对象、Answer、Evidence 和 trace identity 一致。 |
| 2 | Product-only shared fact | Product scope 正确显示，不虚构 Variant。 |
| 3 | Constraint update / withdraw / skip | 约束 chips 与澄清状态可见；服务端确认的新增、修改、撤回和跳过反映到下一轮。 |
| 4 | Two-turn clarification limit | 每轮一个澄清、连续最多两轮；跳过后不自动重复追问。 |
| 5 | 显式跨产品问题 | 本轮对象切换，页面上下文不被静默永久改写。 |
| 6 | 比较请求 | 比较集合和每个成员身份可见，不折叠成单商品。 |
| 7 | 推荐请求 | 最多三款候选，理由与各自 Evidence 绑定。 |
| 8 | RAG 证据不足 | 降级或 fallback；不补写模型常识。 |
| 9 | 动态事实失败/过期 | 不显示旧价格、库存或可售事实。 |
| 10 | 无匹配/状态冲突 | 展示稳定 fallback 与下一步。 |
| 11 | invalid TurnRequest | transport rejection，不进入应用或生成业务 fallback。 |
| 12 | trace audit and client retry | correlation 完整、敏感信息脱敏；不自动重复提交。 |
| 13 | full completion replay | 核心矩阵、完整 suite、scope 和 zero-write evidence 可复现。 |

## 9. Ordered implementation tasks

1. **S07-T01 — Storefront view-model and fallback adapter**：复用现有公共 Envelope，定义客户端安全的内部视图。
2. **S07-T02 — Trace aggregation and redaction**：建立按 Turn 的最小汇总与脱敏 sink，不引入 observability 平台。
3. **S07-T03 — Minimal storefront shell**：实现发送、loading、Answer/Fallback、当前对象和用户触发动作。
4. **S07-T04 — API/storefront integration harness**：接通现有 Conversation API，覆盖 transport 与业务分层。
5. **S07-T05 — Journey and quality baseline**：运行完整 Journey/E2E、静态和安全门禁，记录 provisional 指标。
6. **S07-T06 — Slice completion evidence**：完成矩阵、full suite、zero-write、trace audit 和最终回放证据。

任务必须按顺序执行；LOW/MEDIUM/HIGH 风险及 Workflow Policy 在正式实现前单独确认。若 S07-T01 需要公共 Contract 变化，应立即升级，不得顺手修改。

## 10. Open decisions

- `OD-S07-01`：正式 storefront 技术栈；优先复用现有最小客户端，主要前端依赖需 Human 决策。
- `OD-S07-02`：Trace sink 仅内存/文件回放还是接入现有运行环境；本 Slice 不默认引入平台。
- `OD-S07-03`：Provisional latency/error thresholds 是否调整，以 T05 实验结果为准。
- `OD-S07-04`：Widget 是否需要公开 `target display` 字段；如需要，走版本化 Contract checkpoint。
- `OD-S07-05`：真实 Shopify、模型和客服 smoke 的授权范围与是否阻塞 completion。

## 11. Human escalation

遇到以下情况立即停止：公共 Contract、Product Behavior、Architecture、Accepted Decision、主要依赖、真实外部服务、Shopify write、开放网络、隐私/安全问题、超出前六个 Slice 的功能，或任何放宽 Evidence/Trace 脱敏门禁的要求。

## 12. Completion evidence

Slice 7 只有在所有 S7 Acceptance 和 Matrix 有可回放证据、full suite 与 storefront E2E 通过、trace 脱敏和 zero-write 门禁通过、provisional quality baseline 有处置记录，且未引入未批准的外部依赖或 public Contract 变化后才可关闭。
