# 参考项目分析摘要

> 状态：Canonical Reference Knowledge
> 本文件保存对当前设计仍有长期价值的参考证据。它不是目标系统的 Architecture Source of Truth；如参考实现与已批准设计冲突，以 [ARCHITECTURE.md](./ARCHITECTURE.md) 和 [DECISIONS.md](./DECISIONS.md) 为准。

## 1. Reference Scope

本次设计使用两个本地项目作为输入：

1. **多轮任务型对话项目**：`/Users/russeell/Desktop/三个项目/基于LLM+Agent+MCP的多轮任务型对话系统/项目源码`
2. **车书问答 RAG 项目**：`/Users/russeell/Desktop/三个项目/车书问答系统源码`

结论来自源码、配置、测试/评估脚本和调用链，而不是仅依据 README 或目录名。

## 2. 多轮任务型对话项目

### 2.1 它解决的问题

该项目是一个面向多种意图的多轮任务型问答系统：入口接收请求，读取 Redis 历史，进行 query rewrite、意图/任务识别和工具选择，再在 task、FAQ 与 chat 路径之间仲裁。任务路径通过 function-call 风格的 NLU 选择领域 DM，部分领域再调用 MCP 服务。

主要数据流：

```text
Request
  -> Redis history / query rewrite
  -> intent + task/function prediction
  -> arbitration
  -> task DM / FAQ / chat
  -> optional MCP call
  -> response + logs/history
```

### 2.2 有价值的能力与模式

- 入口层将历史、rewrite、意图判断和下游响应编排为一轮处理，展示了多路径对话系统的真实调用关系。
- 两阶段 NLU 先缩小候选工具，再由模型生成调用，适合作为“有界候选 + 结构化决策”的 Pattern。
- Arbitration 将 task、FAQ 与 chat 分流，证明路由和能力边界应显式存在。
- MCP client/server 与领域 DM 的组合展示了外部工具适配层，但不应反向定义内部 Tool Contract。
- 日志、人工 E2E 评分和意图指标提供了最小可追踪与离线评估实践。

### 2.3 与目标系统的关键差异

- 参考项目以通用意图和多个领域 DM 为中心；目标系统以单品类商品、Variant 资格、证据和 Shopify 动态事实为中心。
- 参考状态主要散布在多份 Redis 历史中，缺少一个带 revision、约束生命周期和对象身份的 ConversationState。
- 路由命中后通常直接进入响应链，缺少 HARD Constraint 的确定性资格引擎、候选拒绝原因和 claim-evidence 绑定。
- 工具 schema 与 handler 存在漂移，失败语义和类型边界不足以支撑 commerce 正确性。

### 2.4 Source Evidence

相对于该参考项目根目录：

- `start.py:117-179`：请求入口、Redis 历史、rewrite、并行判别和主路径编排。
- `client/arbitration.py:85-105`：task / FAQ / chat 仲裁规则。
- `function_call/chatnlu_infer.py:93-126`：两阶段候选工具与 LLM tool-call 流程。
- `function_call/dm/factory.py:13-24`：DMFactory 实际只注册有限领域，暴露 schema/handler 覆盖差异。
- `function_call/function.py:8` 起：大规模工具 schema；Explore 时统计为 455 项、448 个唯一名称，需防止 registry 漂移。
- `mcp_core/mcp_client.py:25-59`：MCP session/call 模式；异常路径存在可能引用未赋值 `result` 的风险。
- `function_call/dm/weather.py:30-53`：具体领域通过 MCP client 连接外部能力。
- `function_call/slot_process.py:32`：使用 `eval` 处理参数，不能进入目标系统信任边界。
- `utils/logger.py:94-128`：全局日志与请求链路记录模式。
- `e2e_score.py:23-58`：人工 E2E 评分入口；Explore 统计为 451/509，约 88.6%。
- `train/result/intent.log:89-93`：意图 Top-1 约 85.73%、Top-5 约 97.49%。
- `train/result/reject.log:88-91`：拒识准确率约 91.14%。
- `log/nlu.log:14` 及相邻记录：真实运行存在 NLU 异常，说明离线指标不能替代链路回放。

## 3. 车书问答 RAG 项目

### 3.1 它解决的问题

该项目面向汽车说明书问答，覆盖文档解析、清洗、父子分块、向量/稀疏检索、结果合并、rerank、回答生成、引用后处理、问答数据生成和评估。其核心价值是展示了从长文档到可引用答案的完整 RAG 链，而不是其具体领域模型或数据库选型。

主要数据流：

```text
PDF / structured source
  -> parse + metadata
  -> chunk / parent-child relation
  -> index
  -> dense + sparse retrieval
  -> merge / optional rerank
  -> generation
  -> citation post-process
  -> offline evaluation
```

### 3.2 有价值的能力与模式

- 文档解析保留标题、页码、层级和 parent-child 关系，为 Evidence locator 和上下文扩展提供基础。
- Hybrid retrieval、父块扩展、rerank 插槽和回答后引用处理可作为可替换 pipeline 的 Pattern。
- 索引构建与在线推理解耦，适合转化为版本化 ingestion/retrieval 边界。
- 同时包含传统指标、语义/关键词评分与 RAGAS 类评估，提醒目标系统将检索和回答分层评估。

### 3.3 与目标系统的关键差异

- 单本车书问答通常在一个文档域内检索；目标系统必须先守住 store/product/variant 范围，再处理多商品证据分配。
- 参考项目把长文档检索作为主真值；目标系统必须将实时 Shopify commerce 事实、结构化 Catalog 和静态文档证据分层。
- 目标系统还需要约束状态、确定性 Variant eligibility、推荐/比较协议、工具错误和可售性刷新，这些不是该 RAG 项目的职责。
- 参考数据生成与划分存在严重泄漏风险，报告分数不能直接作为新系统 baseline。

### 3.4 Source Evidence

相对于该参考项目根目录：

- `build_index.py:17-66`：解析、清洗、分块和索引构建入口。
- `infer.py:27-76`：检索、合并、rerank、生成与后处理的在线主链。
- `src/parser/pdf_parse.py:79-132`：层级元数据与 parent-child ID 的形成。
- `src/utils.py:13-34`：命中子块后扩展/合并父块；`src/utils.py:36-58` 的引用后处理存在编号边界风险。
- `src/retriever/milvus_retriever.py:35-44,114-170`：模块级连接对象与 hybrid retrieval 实现，需隔离连接生命周期和存储依赖。
- `src/client/mongodb_config.py:84-98`：import 时初始化连接/集合，目标系统不应复制这种副作用。
- `src/server/semantic_chunk.py:127-165`：语义分组可能改变原始顺序，需以引用正确性实验验证。
- `src/client/llm_clean_client.py:56-105`：LLM 清洗路径；生成内容不得取代可回溯原文。
- `src/retriever/faiss_retriever.py:27-46`：加载与序列化边界存在安全/正确性风险，不直接复用。
- `src/reranker/qwen3_reranker.py:69-83`：计算后的分数又被覆盖，说明 reranker 必须以排序回归测试验证。
- `src/constant.py:3-20`：硬编码本地路径，不适合目标工程配置。
- `src/gen_qa/run.py:144-164,232-255`：重复生成调用与按改写样本划分造成的数据泄漏风险。
- `final_score.py:50-145`：语义、关键词及 RAGAS 类评估入口，可借鉴分层评估形式。
- `LLaMA-Factory-main/examples/train_lora/qwen3_lora_sft.yaml:12`：样本长度等训练配置被提前固定，不能据此推出目标系统需要微调。

Explore 对生成数据做过交叉核对：验证集中 651 个非“无法回答”样本里，621 个答案文本在训练集中精确出现，约 95.4%。因此该项目的生成式评估分数不能作为目标系统效果证据。

## 4. Reference Decisions

| 能力/资产 | 决策 | 对目标系统的处理 |
|---|---|---|
| 多路径入口、显式 routing | **Adapt** | 收敛为单编排器的有界 RouteDecision，不复制通用多领域 DM 图 |
| 两阶段候选能力选择 | **Pattern** | 先用状态和规则限定可用能力，再允许模型做结构化选择 |
| Redis 对话历史 | **Pattern only** | 借鉴短期缓存；权威状态改为版本化 ConversationState，Redis 不作为唯一真值 |
| MCP client/server | **Adapt / Optional** | 可作外部 adapter；内部 Tool Contract 保持协议无关 |
| 大规模 function schema 注册表 | **Rewrite** | 从 Shopify 售前最小只读能力重建，增加类型、版本和错误语义 |
| 通用聊天与 FAQ fallback | **Pattern** | 保留显式分流和失败分类，不复用宽泛回答逻辑 |
| PDF 解析元数据与 parent-child | **Adapt（待验证）** | 保留来源定位思想；具体 parser/chunk 需用无人机资料验证 |
| Hybrid retrieval pipeline | **Adapt** | 保留可替换 Retriever 与范围过滤；不绑定现有 Milvus 实现 |
| 结果合并、reranker 插槽 | **Pattern** | 以 baseline 驱动是否启用，不直接复用有缺陷实现 |
| 引用后处理 | **Rewrite** | 改为结构化 claim-evidence binding，避免从生成文本猜引用 |
| 离线评估框架 | **Adapt** | 借鉴分层评估，重建无泄漏的商品/多轮 golden set |
| LLaMA-Factory / LoRA 配置 | **不复用** | V1 不以 fine-tuning 为前提，只有评估证明必要时再决策 |
| 领域数据、提示词与模型权重 | **不复用** | 领域、许可、质量和数据分布均不匹配 |
| Shopify Tool Layer、Catalog/Constraint Engine、Evidence Composer | **New** | 两个参考项目均没有满足目标正确性边界的实现 |

## 5. Architecture-impacting Lessons

1. **单一状态模型优先于多份历史拼接。** 参考对话项目的分散历史难以表达撤回、跳过、冲突和并发 revision，因此目标系统建立显式 ConversationState。
2. **内部能力协议不能等同于 MCP 或 function schema。** schema/handler 漂移和 MCP 异常路径表明，稳定的 typed ToolResult、错误语义与 allowlist 才是核心 Contract。
3. **商品身份必须先于检索与生成。** 单文档 RAG 的全局 top-k 不能直接迁移到多商品场景；store/product/variant scope 是强制过滤条件。
4. **动态事实、结构化属性和文档证据分层。** 这是目标正确性的核心边界，而非性能优化。
5. **引用应结构化生成。** 文本后处理容易错号、错商品或丢失来源，Evidence 必须在回答前就携带身份与 locator。
6. **评估数据治理与模型能力同等重要。** 高比例 train/validation 答案重叠使参考分数失真；目标数据必须按原始问题族、文档或产品组合理隔离。
7. **成熟能力只复用边界清晰且可测试的部分。** 连接副作用、硬编码路径、`eval`、分数覆盖和不清晰许可使直接复制成本高于重建接口。

## 6. Known Risks Carried Forward

- Shopify 的实际商品 schema、变体粒度、metafield 完整度和文档授权范围尚未用真实商店验证。
- 无人机手册的排版、表格、扫描质量和跨型号复用情况可能改变 parser/chunk 选择。
- 参考项目未证明多商品 retrieval、实时事实一致性或基于约束的推荐质量。
- 引用的第三方代码副本存在许可证文件/来源完整性疑问；在确认许可证和 provenance 前不复制代码。
- 以上未知项通过 [DECISIONS.md](./DECISIONS.md) 的实验记录收敛，不在本文件中提前决定。
