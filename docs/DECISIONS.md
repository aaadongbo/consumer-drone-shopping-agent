# Architecture and Technical Decisions

> 状态：Decision Log / Source of Truth
> 本文件维护决策记录规则和 ADR 索引。Product Behavior 由 [PROJECT_SPEC.md](./PROJECT_SPEC.md) 定义；模块与 Contract 由 [ARCHITECTURE.md](./ARCHITECTURE.md) 定义。

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
| [DEC-001](./adr/DEC-001-query-rewrite.md) | OPEN | Query Rewrite 何时启用？ | 默认关闭；只把 gated rewrite 作为实验候选 |
| [DEC-002](./adr/DEC-002-chunking.md) | OPEN | 文档如何 Chunking？ | 以保序、可定位的 heading-aware baseline 开始实验 |
| [DEC-003](./adr/DEC-003-multi-product-retrieval.md) | OPEN | Multi-product Retrieval 如何分配候选？ | 比较 global top-k、per-product quota 和 two-stage |
| [DEC-004](./adr/DEC-004-reranker.md) | OPEN | 是否使用 Reranker？ | 先建立无 reranker baseline，再验证通用 reranker |
| [DEC-005](./adr/DEC-005-fine-tuning.md) | OPEN | V1 是否需要 Fine-tuning？ | 不作为 V1 前提；只有明确误差证据时评估 |
| [DEC-006](./adr/DEC-006-recommendation-ranking.md) | OPEN | 软偏好 Recommendation Ranking 如何实现？ | 确定性透明规则作为 baseline，不按利润/热度排序 |
| [DEC-007](./adr/DEC-007-milvus.md) | OPEN | 是否采用 Milvus？ | 可替换候选，不是 Architecture Requirement |
| [DEC-008](./adr/DEC-008-single-bounded-orchestrator.md) | ACCEPTED | 单编排器还是 Multi-Agent？ | V1 使用单一有界 orchestrator |
| [DEC-009](./adr/DEC-009-dynamic-commerce-facts-separate-from-rag.md) | ACCEPTED | Shopify 动态事实与 RAG 如何分工？ | 动态 commerce 事实与静态文档知识严格分层 |
| [DEC-010](./adr/DEC-010-deterministic-hard-constraints-at-variant-level.md) | ACCEPTED | HARD Constraint 由谁判断？ | 由确定性 Variant 级代码判断 |
| [DEC-011](./adr/DEC-011-protocol-independent-internal-tool-contract.md) | ACCEPTED | 内部 Tool Contract 是否依赖 MCP？ | 协议无关；MCP 仅是可选 adapter |
| [DEC-012](./adr/DEC-012-separate-page-context-turn-target-and-conversation-context.md) | ACCEPTED | 商品页、单轮目标与长期会话对象如何分工？ | Page Context 提供默认，Turn Target 约束本轮，只有确认切换更新 Conversation Context |
| [DEC-013](./adr/DEC-013-bounded-agentic-rag-only.md) | ACCEPTED | V1 是否采用 Agentic RAG？ | 只采用单编排器内受限 ActionPlan，不采用开放式 ReAct / 多 Agent |

## 3. Decision Evidence Notes

- `DEC-012` accepted on 2026-09-05 by Human reconciliation after Slice 3 through
  Slice 10 implemented and depended on the Page Context / Turn Target /
  Conversation Context separation semantics. This updates only the Decision status
  and evidence in this index; it does not change the Decision content boundary,
  public Contract, Product Behavior, or Architecture text.
