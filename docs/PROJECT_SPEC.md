# 消费级无人机智能导购 Agent — PROJECT SPEC V1

> 状态：V1 Draft / Source of Truth for WHAT & WHY
> 更新原则：本文件定义产品应表现成什么样，以及如何判断 V1 完成。实现方式由 [ARCHITECTURE.md](./ARCHITECTURE.md) 维护；尚待实验的技术选择由 [DECISIONS.md](./DECISIONS.md) 维护。

## 1. Problem

Shopify 消费级无人机商店的售前用户通常不会用完整、结构化的条件描述需求。他们可能先问一个宽泛问题，随后补充预算、使用场景、重量、续航、画质、便携性等限制，也可能撤回或修改之前的条件。

传统关键词搜索、静态 FAQ 或单轮聊天容易出现以下问题：

- 未持续维护用户约束，导致后续推荐与前文冲突。
- 把偏好误当成硬性条件，或把硬性条件当作可妥协偏好。
- 混淆商品与变体，组合出并不存在的价格、配置或库存。
- 用非实时资料回答价格、库存和可售状态。
- 给出推荐结论却无法说明证据来源。
- 在无匹配商品、资料缺失或工具失败时猜测答案。

## 2. Goal

为单一 Shopify 商店提供一个面向消费级无人机售前咨询的对话式智能导购助手。V1 应形成以下可验证闭环：

用户表达或逐步澄清需求 → 系统维护约束 → 筛选可售变体 → 回答、比较或推荐商品 → 展示支持关键结论的证据 → 在无法可靠完成时明确降级。

系统的核心价值不是“像人一样自由聊天”，而是以可追踪的状态、结构化商品事实和商家授权资料，帮助用户缩小选择范围并做出更有依据的购买判断。

## 3. Scope

### 3.1 V1 Must Have

- 面向单一 Shopify 商店、简体中文、消费级无人机品类。
- 以正式店面聊天组件承载咨询体验。
- 支持渐进式或流式反馈，并提供可验证的结构化最终响应；具体传输协议属于 Architecture Design Choice。
- 支持单轮咨询和多轮需求澄清。
- 维护并展示当前有效约束，允许用户新增、修改、撤回或跳过约束。
- 区分硬约束与软偏好。
- 基于结构化商品与变体数据执行确定性硬约束筛选。
- 支持商品搜索、候选缩小、最多三款商品推荐。
- 支持二至四款商品或具体变体的比较。
- 支持商品事实、使用说明、FAQ 和适用政策问答。
- 对推荐理由、关键比较结论和事实回答提供可定位证据。
- 价格、库存和可售状态以 Shopify 当前数据为准。
- 对无匹配、资料不足、商品不可售、工具失败、越界问题提供明确 fallback。
- 记录足够的评估与追踪信息，使行为可复现、可诊断。

### 3.2 Later

以下能力合理，但不应阻塞 V1：

- 更多商品品类、多商店和多语言。
- 个性化长期用户画像与跨会话偏好学习。
- 外部评测、社区内容和开放网络资料接入。
- 更丰富的运营后台、实验平台和人工标注工作台。
- 多模态图片、视频或语音咨询。
- 主动营销、推荐活动或复杂销售自动化。
- 复杂的领域模型训练、微调或领域专用 reranker。
- 更高级的个性化排序和学习排序。

## 4. Non-Goals

V1 明确不做：

- 购物车、结账、订单、退款、账号等写操作。
- 代替用户作出具有约束力的购买决定。
- 对航空法规、飞行许可或安全合规给出权威法律结论。
- 在商家资料缺失时猜测参数、兼容性、库存或政策。
- 把未知字段当作“不支持”，或让未知值自动通过硬约束。
- 使用外部评论、开放网络搜索或未经商家授权的内容作为证据。
- 构建开放式自治多 Agent 系统。
- 让模型通过无限工具循环、开放网络或未经授权资料自行补齐证据。
- 将 fine-tuning 作为 V1 交付前提。
- 预先维护完整实现文件树。

## 5. Core User Journeys

### 5.1 商品页事实问答

用户在某个商品页询问“这款能飞多久”“是否支持某功能”或“包装里有什么”。当前页面商品与已选套装是默认 Page Context，但不是永久锁定：用户显式询问其他商品时，本轮应以显式对象为准。系统基于结构化商品事实或官方资料回答，并给出证据。若问题中的商品或具体配置不明确，系统请求澄清，不默认选择第一个商品或变体。

### 5.2 单轮推荐

用户一次性给出较完整需求，例如预算、用途、重量和画质偏好。系统解析约束，筛选可售变体，返回最多三款不同商品及匹配理由、关键取舍和证据。

### 5.3 多轮澄清与推荐

用户从宽泛目标开始。系统每轮最多追问一个最有区分度的缺失条件，连续追问最多两轮。用户可以跳过问题；被明确跳过或放弃的维度不会反复追问。信息足够时，系统给出正式推荐；信息不足但仍可提供价值时，只给出明确标注为暂定的候选。

### 5.4 约束更新、冲突与撤回

用户可说“预算改成 5000”“重量无所谓了”“必须低于 250 克”等。系统更新可见约束，并以最新有效状态继续筛选。若新旧约束冲突，系统指出冲突并请求用户确认，而不是静默覆盖或自行妥协。

### 5.5 商品比较

用户比较二至四款商品或变体。系统按同一组相关维度展示差异，并区分已知、不适用和未知。若用户只指定商品而未指定变体，系统选择最符合当前约束的可售变体并明确披露该选择。

### 5.6 无匹配或不可可靠回答

当没有变体满足全部硬约束、资料不足、商品不可售或依赖服务失败时，系统说明原因，展示导致无匹配的约束或缺失信息，并提供下一步选择，例如放宽某项条件、稍后重试或联系人工支持。系统不得伪造结果。

## 6. Required Product Behavior

### 6.1 对话与约束

- 系统必须维护当前会话的有效需求状态，而不是只依赖最近一条消息。
- 系统必须区分 Page Context、Turn Target 与 Conversation Context：页面提供默认对象，本轮解析结果决定实际回答对象，只有已确认的长期上下文可供后续代词继承。
- 目标解析优先级为：用户显式指定的 Product / Variant > 已确认的 Conversation Context > 当前 Page Context > 请求澄清。
- 用户显式指定其他商品时，Page Context 不得覆盖显式对象；单次临时跨产品提问不得静默修改 Conversation Context。
- 只有用户明确要求切换，或确认待处理的切换后，后续代词才继承新的 Conversation Context。
- 比较请求保留多个对象，不能被误处理为单商品切换；推荐请求面向商店候选，不能被当前商品页限制；全站支持意图应移交相应能力而不是伪装成当前商品事实问答。
- Answer、Product Card、Evidence 与 claim bindings 必须统一指向本轮 Turn Target；跨产品查询不得混入 Page Context 商品的规格、价格或库存。
- 用户可见结果应明确展示当前回答对象；商品或 Variant 不明确时必须澄清，不默认选择第一个。
- 约束必须支持新增、更新、撤回、确认冲突和明确跳过。
- 明确措辞“必须、不能、不超过、至少、只考虑、预算 X 以内”等默认解释为硬约束。
- “最好、希望、偏向、尽量、轻一点”等默认解释为软偏好；上下文可改变判断，但必须可追踪。
- 当前约束应以用户可见、可编辑的形式呈现。
- 每轮最多提出一个澄清问题，连续澄清最多两轮。
- 正式推荐前必须具备足够条件；条件不足时只能给出暂定候选并说明缺口。

### 6.2 商品筛选与推荐

- 硬约束资格判断必须落在具体 Variant 上，界面可按 Product 分组展示。
- 只有当前可售的变体可进入正式推荐。
- 缺失某硬约束所需字段的变体不得被视为满足该约束。
- 推荐结果最多包含三款不同商品，且不得混合不同变体的属性形成不存在的组合。
- 推荐理由必须说明满足了哪些重要条件、存在什么取舍，以及依据是什么。
- 当没有任何变体满足全部硬约束时，不得输出正式推荐。

### 6.3 比较

- 比较必须针对具体变体执行；商品级比较必须披露系统代选的变体。
- 比较项应优先覆盖用户当前约束与购买决策相关维度，而不是固定堆叠所有字段。
- 未知值必须显示为未知，不得解释为不支持或零。
- 同一结论引用的证据必须属于相应商品或变体。

### 6.4 商品问答与证据

- 结构化目录用于确定性的商品与变体事实；官方文档用于说明、FAQ、手册和政策内容。
- 可接受的证据来源仅包括 Shopify 商家授权数据及商家提供或认可的官方资料。
- 推荐的关键理由、关键比较事实和直接商品事实回答必须能关联到证据。
- 证据不足时必须说明无法确认，而不是依靠模型常识补全。
- 需要多步补证时，只能使用受限、可审计的 Agentic RAG：每轮 ActionPlan 必须有明确 Turn Target、约束、工具预算和 allowlist；Evidence Gate 拥有最终否决权。V1 的 `max_action_rounds = 2 total`，第 1 轮包含初始检索或读取，最多再执行一轮纠正。
- 受限 Agentic RAG 不得改变 Product / Variant identity、用户约束或证据范围；预算耗尽、证据错配、资料缺失或工具失败时必须 fail closed。

### 6.5 动态事实与只读边界

- 价格、库存和可售状态必须使用当前 Shopify 数据，并向用户披露必要的新鲜度信息。
- 系统只能执行读取类 Shopify 操作。
- 系统不得创建或修改购物车、订单、客户、商品、库存或其他商店状态。

### 6.6 Fallback

系统至少必须可区分并处理：

- 没有满足硬约束的商品。
- 约束之间发生冲突。
- 关键用户条件缺失。
- 关键商品字段或证据缺失。
- 商品或变体当前不可售。
- Shopify 或检索服务暂时失败。
- 授权失败或会话状态失效。
- 请求超出售前导购范围。
- 法规或安全问题需要权威来源或人工确认。

## 7. Acceptance Criteria

V1 只有在以下行为可通过预定义案例独立验证时，才视为完成：

1. 用户可以从宽泛需求开始，在不超过两次连续澄清后获得正式推荐、暂定候选或明确说明仍缺什么。
2. 用户对预算、用途、重量等约束的新增、修改、撤回与跳过，会反映在可见状态和下一轮结果中。
3. 硬约束始终在可售 Variant 层级验证，且无硬匹配时不会生成正式推荐。
4. 单次正式推荐不超过三款不同商品，不出现跨变体属性混合。
5. 比较二至四款商品或变体时，系统披露实际比较的变体，并正确显示未知值。
6. 商品事实问答、关键比较结论和推荐理由带有属于正确商品或变体的证据。
7. 价格、库存和可售状态来自当前 Shopify 读取结果；动态事实不可由陈旧文档冒充实时信息。
8. Shopify 依赖不可用、证据不足或请求越界时，系统返回可理解、可行动的 fallback，不伪造答案。
9. 所有 Shopify 工具均为只读；测试和运行日志中不存在写调用。
10. 关键回放信息完整：输入状态、状态变化、路由、工具结果、候选筛除、证据、回答和失败原因可关联到同一轮次。
11. 商品页上的显式跨产品问题以显式对象作为 Turn Target，临时问答不污染 Conversation Context；明确切换后后续代词才继承新对象。
12. 比较、推荐与全站支持请求按其自身目标类型路由；回答对象展示以及 Answer、Card、Evidence、bindings 的身份均与 Turn Target 一致，歧义时不默认选择商品或 Variant。
13. Product RAG 只能在 Turn Target 限定的单一 store/product/variant 和授权文档版本内检索；若 `max_action_rounds = 2 total` 内仍无支持证据，不得生成事实结论。
14. 多商品推荐的每个候选只能使用自身 Catalog、Shopify 和文档 Evidence；Derived Evidence 必须可复算并绑定来源，证据不足的理由必须降级或删除。

## 8. Provisional Quality Gates

以下数值是 V1 当前的临时目标，不是已经证明可行的永久要求。建立代表性 baseline 数据集后，应根据任务难度、样本置信区间、成本和用户影响复核；任何调整都需要记录理由。

| 维度 | 临时目标 | 口径说明 |
|---|---:|---|
| 约束抽取与更新准确率 | ≥ 90% | 字段、操作、值、单位、硬软属性与撤回动作综合判断 |
| 最终有效状态准确率 | ≥ 90% | 多轮结束时的有效约束集合与人工标注一致 |
| 硬约束满足率 | ≥ 95% | 正式推荐中的变体满足全部可验证硬约束 |
| 路由准确率 | ≥ 90% | 对预定义用户旅程和 fallback 类型的决策正确 |
| 商品/变体混淆率 | < 1% | 不存在跨变体拼接或引用对象错配 |
| Evidence Recall@5 | ≥ 85% | 需文档证据的问题在前五条证据中命中支持内容 |
| 引用正确率 | ≥ 95% | 引用确实支持相邻结论且归属正确商品/变体 |
| 关键结论证据覆盖率 | ≥ 90% | 应举证的推荐、比较和事实结论具有证据绑定 |
| No-match / Fallback 正确率 | ≥ 90% | 失败原因分类及建议动作符合标注 |
| 首个可见响应时间 p95 | ≤ 3 秒 | 从提交用户输入到首个可见响应或状态反馈 |
| 完整回答时间 p95 | ≤ 12 秒 | 从提交用户输入到结构化回答完成 |

### 8.1 不可妥协的安全与正确性门槛

以下项目不因 provisional 指标调整而放宽：

- Shopify 写操作为零。
- 不跨商店读取或混用数据。
- UNKNOWN 不得表达为“不支持”。
- 陈旧资料不得伪装成实时价格、库存或可售状态。
- 不得混合不同变体的属性。
- 证据不得错误归属到其他商品或变体。
- 密钥、令牌和敏感配置不得进入回答、日志或 trace。
- 无硬约束匹配时不得输出正式推荐。

## 9. Development Strategy — Vertical Slices

开发按可独立运行和验证的用户闭环推进，而不是先横向完成所有基础设施。以下是 Slice 级路线，不是 Coding Task 清单；每个 Slice 的实现计划只在该 Slice 即将开始时建立。

### Slice 1：商品页事实查询最小 E2E

- **User Journey**：用户在商品页询问当前商品或变体的一个结构化事实。
- **Goal**：打通用户输入、页面上下文、路由、只读商品事实、响应、证据和最小 trace。
- **Acceptance**：能准确识别页面商品/变体；回答带正确对象的证据；事实缺失或对象不明确时明确 fallback；不存在 Shopify 写调用。
- **关键依赖**：Turn、商品/变体身份、ToolResult、Evidence、AnswerEnvelope 的最小 Contract；可控的 Shopify fixture 或 adapter stub。
- **主要 Open Decisions**：流式传输方式及动态事实刷新窗口；不要求先决定 RAG、Milvus 或模型微调。

### Slice 2：单轮约束推荐

- **User Journey**：用户一次给出预算、用途、重量或功能要求，并获得不超过三款商品建议。
- **Goal**：验证约束抽取、Variant 级硬过滤、Product 分组呈现和透明的软偏好基线。
- **Acceptance**：HARD/SOFT 区分可追踪；只有可售且满足所有已知硬约束的变体进入正式推荐；无匹配时解释阻断约束；不跨变体拼接属性。
- **关键依赖**：ConstraintPatch、规范化 Catalog、eligibility 结果、Recommendation 与 Evidence Contract。
- **主要 Open Decisions**：软偏好 Recommendation Ranking；缺失属性治理阈值。

### Slice 3：Target Resolution 与最小上下文状态

- **User Journey**：用户在商品页沿用“这款/它/这个套装”，临时询问其他商品，或明确切换回答对象；比较、推荐和全站支持意图被正确分类并移交。
- **Goal**：建立 Page Context、Turn Target 与已确认 Conversation Context 的最小、可审计语义，避免页面默认对象覆盖显式目标或临时问题污染长期上下文。
- **Acceptance**：显式 Product / Variant 优先于已确认 Conversation Context 和 Page Context；临时跨产品问答只改变本轮 Turn Target；明确切换或确认后才更新 Conversation Context；歧义时澄清且不默认选择；比较不变成单商品切换，推荐不被当前页面限制；Answer、Card、Evidence、bindings 与用户可见回答对象统一指向 Turn Target。
- **关键依赖**：TurnRequest Page Context、最小 TargetResolution / TurnTarget、ConversationState revision 与幂等、Product / Variant identity、RouteDecision、Evidence 与 AnswerEnvelope identity gate。
- **主要 Open Decisions**：Product / Variant alias 与歧义基线、最小 target display wire 形状、持久化 adapter 的接入时点；Query Rewrite 不得替代目标解析或直接修改 Conversation Context。
- **边界**：本 Slice 只建立目标与切换所需的最小状态，不完成约束新增/修改/撤回/跳过的完整多轮闭环。该 V1 行为仍保留，须在 Slice 3 Completion Review 后通过后续 Slice planning reconciliation 明确承接位置，不能被视为已完成或删除。

### Slice 4：Variant 比较

- **User Journey**：用户要求比较二至四款商品或具体变体，并关注与当前需求相关的差异。
- **Goal**：验证 Product/Variant 身份边界、规范化属性和面向决策的比较表达。
- **Acceptance**：实际比较对象明确；Product 级请求会披露所选 Variant；KNOWN、UNKNOWN、NOT_APPLICABLE 不混淆；每项关键结论证据归属正确。
- **关键依赖**：VariantRecord、AttributeValue、comparison set、Evidence 与结构化比较输出。
- **主要 Open Decisions**：商品级请求的变体代选规则是否需要基于评估调整。

### Slice 5：Product RAG

- **User Journey**：用户询问手册、FAQ、包装内容、操作或适用政策中的非实时知识。
- **Goal**：在限定商店与商品范围内完成可回溯的文档检索、受限 ActionPlan 补检、回答和引用。
- **Acceptance**：证据可定位到原始资料；不跨商品误引；资料不足时不补写常识；动态价格、库存和可售状态不从文档回答；`max_action_rounds = 2 total` 内仍不足则 fallback。
- **关键依赖**：文档范围/版本、Retriever、Evidence locator、claim-evidence binding Contract 以及首批评估集。
- **主要 Open Decisions**：Chunking、Query Rewrite、Reranker、检索引擎（含 Milvus）、召回参数和 ActionPlan 是否需要模型参与。

### Slice 6：多商品 Evidence-based Recommendation

- **User Journey**：用户在多个候选中获得带适配理由、取舍和多来源证据的正式推荐。
- **Goal**：组合确定性候选、动态 Shopify 事实、商品范围内文档证据和可复算 Derived Evidence，形成完整推荐解释。
- **Acceptance**：最多推荐三款不同商品；每款使用自身证据；硬约束资格与解释一致；动态 commerce 与静态 RAG 分离；证据不足的理由被降级或删除；无匹配时不生成正式推荐。
- **关键依赖**：稳定的 eligibility、multi-product Evidence、Recommendation、Composer 和 trace Contract。
- **主要 Open Decisions**：Multi-product Retrieval 候选配额、软偏好 Recommendation Ranking、是否启用 Reranker。

### Slice 7：Fallback / Trace / 正式店面闭环

- **User Journey**：用户在正式店面完成上述旅程，并在超时、无匹配、资料不足或状态冲突时获得可行动反馈。
- **Goal**：补齐店面体验、失败协议、可观测性和发布前 E2E 质量闭环。
- **Acceptance**：核心旅程与失败案例可在正式组件回放；trace 能关联输入、状态、路由、工具、候选、证据和回答；敏感信息不进入输出或 trace；Provisional Quality Gates 有 baseline 结果与处置记录。
- **关键依赖**：前六个 Slice 的稳定 Contract、标准 fallback、评估数据集和运行环境配置。
- **主要 Open Decisions**：Provisional 指标是否调整；超时/重试预算；是否有证据支持引入 fine-tuning 或更复杂检索组件。

## 10. Artifact Evolution and Source of Truth

后续 Evidence 或 Discovery 触发以下流程：

```text
Discovery
  ↓
Impact Analysis
  ↓
Spec？Architecture？Contract？Decision？Task？
  ↓
Reconcile
  ↓
更新对应 Source of Truth
```

- Product Behavior、Scope、Acceptance 与质量门槛以本文件为 Source of Truth。
- Architecture、模块职责边界与核心 Contract 以 [ARCHITECTURE.md](./ARCHITECTURE.md) 为 Source of Truth。
- Reference Knowledge 以 [REFERENCE_ANALYSIS.md](./REFERENCE_ANALYSIS.md) 为 Source of Truth。
- 重大 Architecture / Technical Decisions 及其历史以 [DECISIONS.md](./DECISIONS.md) 为 Source of Truth。
- 完整 Project Tree 以真实 Repository 为 Source of Truth；高层文档只描述具有设计意义的模块边界。
- 改变 Product Behavior 时更新本文件；改变模块边界或核心 Contract 时更新 Architecture；改变重大技术取舍时更新 Decisions。
- 只有局部实现细节或文件级 Tree 变化、且模块边界未变时，不更新高层 Artifact。
- Evidence 证明旧设计错误时，应 Reconcile Artifact，而不是要求代码机械服从旧设计。
- Slice 进度、Coding Task 和工作状态等到正式进入相应 Slice 时再建立；若提前创建远期 Slice 规划 Artifact，必须明确标记为 draft/non-executable，不得形成可执行 Task 状态。
