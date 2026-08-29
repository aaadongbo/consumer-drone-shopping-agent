# Architecture and Technical Decisions

> 状态：Decision Log / Source of Truth
> 本文件记录重要取舍、开放实验及替代历史。Product Behavior 由 [PROJECT_SPEC.md](./PROJECT_SPEC.md) 定义；模块与 Contract 由 [ARCHITECTURE.md](./ARCHITECTURE.md) 定义。

## 1. Record Rules

- `OPEN`：现有证据不足，当前选择仅是 baseline 或候选，不是固定 Architecture Requirement。
- `ACCEPTED`：已有足够的产品、正确性或工程依据，当前 V1 采用该选择。
- `SUPERSEDED`：已被后续 Decision 替代；记录保留，并链接替代它的新 Decision。
- 新 Evidence 先做 Impact Analysis，再更新相应 Decision、Architecture、Spec 或 Slice 工作项。
- 新方案替代旧方案时不删除旧记录；旧项标记 `SUPERSEDED`，新项明确 `Supersedes` 关系。
- `Result` 只填写实际完成的验证结论；未实验时不得把预期写成结果。

## 2. Decision Index

| ID | Status | Question | Current Choice |
|---|---|---|---|
| DEC-001 | OPEN | Query Rewrite 何时启用？ | 默认关闭；只把 gated rewrite 作为实验候选 |
| DEC-002 | OPEN | 文档如何 Chunking？ | 以保序、可定位的 heading-aware baseline 开始实验 |
| DEC-003 | OPEN | Multi-product Retrieval 如何分配候选？ | 比较 global top-k、per-product quota 和 two-stage |
| DEC-004 | OPEN | 是否使用 Reranker？ | 先建立无 reranker baseline，再验证通用 reranker |
| DEC-005 | OPEN | V1 是否需要 Fine-tuning？ | 不作为 V1 前提；只有明确误差证据时评估 |
| DEC-006 | OPEN | 软偏好 Recommendation Ranking 如何实现？ | 确定性透明规则作为 baseline，不按利润/热度排序 |
| DEC-007 | OPEN | 是否采用 Milvus？ | 可替换候选，不是 Architecture Requirement |
| DEC-008 | ACCEPTED | 单编排器还是 Multi-Agent？ | V1 使用单一有界 orchestrator |
| DEC-009 | ACCEPTED | Shopify 动态事实与 RAG 如何分工？ | 动态 commerce 事实与静态文档知识严格分层 |
| DEC-010 | ACCEPTED | HARD Constraint 由谁判断？ | 由确定性 Variant 级代码判断 |
| DEC-011 | ACCEPTED | 内部 Tool Contract 是否依赖 MCP？ | 协议无关；MCP 仅是可选 adapter |

## 3. Open Decisions

### DEC-001 — Query Rewrite

- **Status**：OPEN
- **Question**：哪些承接、省略、指代或长对话场景需要 Query Rewrite？
- **Context**：参考对话项目在主链中普遍 rewrite，但商品名称、数值、单位、否定和 HARD/SOFT 语义一旦被改写错误，会污染状态与检索。原始用户文本必须始终保留。
- **Current Choice**：V1 baseline 默认不 rewrite。实验候选为仅在明确的指代消解或检索失败条件下产生辅助查询；辅助查询不得覆盖原文或直接修改 ConversationState。
- **Rationale / Evidence**：参考项目证明 rewrite 可改善上下文承接，但没有商品约束保真证据；目标风险高于一般 FAQ。
- **Validation Method**：构建含型号、预算、单位、否定、撤回、代词和跨轮省略的标注集，对比 off、always-on、gated 三组；测量约束保真、实体保持、retrieval recall、最终回答正确率和额外延迟。
- **Result**：尚未执行。
- **Affected Artifacts**：Architecture 的 State、Router、RAG 输入；Slice 3、5、6。

### DEC-002 — Chunking

- **Status**：OPEN
- **Question**：无人机商品页、FAQ 和手册应采用何种分块策略？
- **Context**：参考 RAG 项目提供标题层级和 parent-child 模式，但语义分组可能改变原文顺序。无人机资料还可能包含规格表、警告、脚注和跨页步骤。
- **Current Choice**：从保持原始顺序和 locator 的 heading-aware overlap baseline 开始；parent-child 与表格感知策略作为实验组。
- **Rationale / Evidence**：可回溯性是硬边界，而最佳块大小取决于真实资料分布。
- **Validation Method**：建立覆盖事实、步骤、限制、表格和跨段问题的数据集；比较 Evidence Recall@k、引用正确率/完整性、上下文 token、重复率和解析失败率。
- **Result**：尚未执行。
- **Affected Artifacts**：RAG ingestion/retrieval；Slice 5、6。

### DEC-003 — Multi-product Retrieval

- **Status**：OPEN
- **Question**：同时解释多个候选时，证据预算应如何在商品间分配？
- **Context**：全局 top-k 容易被文档量大或语义相似的一款商品占满；固定 per-product quota 可能浪费预算；two-stage 增加延迟与复杂度。
- **Current Choice**：不固定算法。用 global top-k、per-product quota 和先选商品后商品内检索的 two-stage 三组建立对照。
- **Rationale / Evidence**：两个参考项目都没有证明多商品证据覆盖策略。
- **Validation Method**：以二至三款商品的推荐/比较题评估 gold-product coverage、每商品 Evidence Recall、引用归属正确率、答案覆盖、token 与 p95 latency。
- **Result**：尚未执行。
- **Affected Artifacts**：Retriever、Evidence Composer；Slice 6。

### DEC-004 — Reranker

- **Status**：OPEN
- **Question**：是否需要 reranker，若需要是否需领域训练？
- **Context**：参考项目有 reranker 插槽，但其 Qwen 实现存在分数被覆盖风险。Reranker 只有在显著改善端到端证据质量时才值得引入延迟和运维成本。
- **Current Choice**：先测无 reranker baseline；再测试一个通用 reranker。领域训练不属于初始方案。
- **Rationale / Evidence**：当前没有干净的无人机领域对照结果。
- **Validation Method**：固定 candidate set，对比 nDCG/Recall@k、引用正确率、answer correctness、p95 latency 和单位请求成本；仅在置信区间内有稳定净收益时启用。
- **Result**：尚未执行。
- **Affected Artifacts**：RAG retrieval pipeline；Slice 5、6。

### DEC-005 — Fine-tuning

- **Status**：OPEN
- **Question**：Prompt、规则、Catalog 和 RAG baseline 后是否仍需模型微调？
- **Context**：参考 RAG 项目含 LoRA 流程，但评估集存在高比例答案泄漏，不能证明微调必要或有效。
- **Current Choice**：Fine-tuning 不是 V1 依赖，也不在 baseline 前实施。只有稳定、可归因且无法通过数据/Contract/提示修复的误差才触发实验。
- **Rationale / Evidence**：降低数据治理、模型版本和部署复杂度；避免用训练掩盖系统边界问题。
- **Validation Method**：先完成模块和 E2E error taxonomy；若特定任务有足够无泄漏样本且 baseline 持续不达标，再做相同数据划分下的受控对照，评估质量、泛化、成本和回归。
- **Result**：尚未触发实验。
- **Affected Artifacts**：模型 adapter、Evaluation；潜在 Later scope。

### DEC-006 — Recommendation Ranking

- **Status**：OPEN
- **Question**：通过 HARD eligibility 后，如何根据 SOFT preferences 对候选排序？
- **Context**：V1 的目标是用户适配，不是利润、库存去化或流行度最大化。排序必须可解释、稳定且不能让软分数覆盖硬条件。
- **Current Choice**：使用透明、确定性的软偏好匹配规则作为 baseline；权重和更复杂方法保持开放。
- **Rationale / Evidence**：规则 baseline 最容易审计并支持早期标注；当前没有行为数据支持 learning-to-rank。
- **Validation Method**：建立带偏好强度和成对人工选择的推荐集；评估 hard-violation、pairwise agreement、top-k usefulness、解释一致性、稳定性与无匹配行为。
- **Result**：尚未执行。
- **Affected Artifacts**：Catalog/Constraint Engine、Recommendation output；Slice 2、6。

### DEC-007 — Milvus

- **Status**：OPEN
- **Question**：Milvus 是否是 V1 合适的检索存储？
- **Context**：参考 RAG 项目已有 Milvus hybrid retrieval，但目标数据规模、metadata filtering、部署环境和运维能力尚未验证。Architecture 需要的是可过滤、版本化、可评估的 Retriever，不是特定产品。
- **Current Choice**：Milvus 是 Provisional Design Choice；在建立 corpus 与 retrieval benchmark 前不写成硬依赖。
- **Rationale / Evidence**：复用思路有价值，但参考实现有模块级连接副作用且真实规模未知。
- **Validation Method**：使用实际 corpus 比较候选引擎的 metadata filter 正确性、hybrid 支持、Recall@k、索引/查询延迟、更新删除、备份恢复、开发与运维成本。
- **Result**：尚未执行。
- **Affected Artifacts**：RAG adapter、部署配置；Slice 5。

## 4. Accepted Architecture Decisions

### DEC-008 — Single Bounded Orchestrator

- **Status**：ACCEPTED
- **Question**：V1 使用单编排器还是开放式 Multi-Agent？
- **Context**：V1 用户旅程有限，正确性依赖稳定状态、工具预算和职责边界；多 Agent 会增加状态一致性、trace 和评估难度。
- **Current Choice**：一个有界 Agent/Router 协调 State、Catalog、Shopify、RAG 和 Composer；不采用自治 Agent 间协商。
- **Rationale / Evidence**：参考对话项目的显式 arbitration 已足以支撑能力路由；目标范围没有需要自治多 Agent 的证据。
- **Validation Method**：通过七个 Vertical Slice 的 journey eval 验证可覆盖性；若未来出现单编排器无法表达的独立权限/生命周期，再开新 Decision。
- **Result**：设计评审已接受；实现验证待各 Slice 完成。
- **Affected Artifacts**：[ARCHITECTURE.md](./ARCHITECTURE.md) Agent/Router 边界；全部 Slice。

### DEC-009 — Dynamic Commerce Facts Separate from RAG

- **Status**：ACCEPTED
- **Question**：价格、库存、可售状态是否可以由文档索引回答？
- **Context**：这些事实随时变化，文档索引具有不可避免的滞后。
- **Current Choice**：动态 commerce 事实由 Shopify 只读 Tool 在回答时按策略获取/刷新；RAG 只承载商家授权的相对静态知识。
- **Rationale / Evidence**：避免陈旧事实误导购买决策，并允许独立的新鲜度与失败语义。
- **Validation Method**：Contract/E2E 测试注入文档与 Shopify 不一致数据，确认动态事实始终采用当前 ToolResult 并披露新鲜度。
- **Result**：设计评审已接受；实现验证待 Slice 1、6、7。
- **Affected Artifacts**：[PROJECT_SPEC.md](./PROJECT_SPEC.md) 动态事实行为；Architecture 的 Shopify/RAG/Evidence 边界。

### DEC-010 — Deterministic HARD Constraints at Variant Level

- **Status**：ACCEPTED
- **Question**：正式推荐的硬约束资格由模型还是确定性逻辑判断？
- **Context**：预算、重量、功能与可售性直接决定候选合法性；模型自由判断不可稳定复现，也容易混淆 Product/Variant。
- **Current Choice**：HARD eligibility 由 Catalog/Constraint Engine 对具体 Variant 以确定性代码判断；UNKNOWN 不通过对应硬约束。模型可解析表达，但不能覆盖结果。
- **Rationale / Evidence**：这是满足无硬违规、可审计和无跨变体拼接的必要条件。
- **Validation Method**：规则属性测试、边界值和单位测试、unknown/missing fixtures，以及 recommendation E2E hard-violation gate。
- **Result**：设计评审已接受；实现验证待 Slice 2、4、6。
- **Affected Artifacts**：[PROJECT_SPEC.md](./PROJECT_SPEC.md) 筛选行为；Architecture 的 Catalog 与 Recommendation Contract。

### DEC-011 — Protocol-independent Internal Tool Contract

- **Status**：ACCEPTED
- **Question**：内部 Shopify 能力是否直接以 MCP schema 作为领域接口？
- **Context**：MCP 是有用的互操作协议，但参考项目显示 schema/handler 漂移和异常语义不足；目标系统需要稳定 typed data、store scope、freshness 和错误分类。
- **Current Choice**：内部 Tool Contract 与 MCP 解耦；MCP 只在有外部互操作需求时作为 adapter。
- **Rationale / Evidence**：保护领域模块不受传输协议和 SDK 生命周期影响，同时保留未来 MCP 接入能力。
- **Validation Method**：对内部 adapter 和可选 MCP adapter 运行同一组 contract tests，验证数据、错误和只读 allowlist 等价。
- **Result**：设计评审已接受；实现验证待 Slice 1。
- **Affected Artifacts**：[ARCHITECTURE.md](./ARCHITECTURE.md) Shopify Tool Layer；Slice 1。
