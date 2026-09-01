# DEC-004 — Reranker

- **Status**：OPEN
- **Question**：是否需要 reranker，若需要是否需领域训练？
- **Context**：参考项目有 reranker 插槽，但其 Qwen 实现存在分数被覆盖风险。Reranker 只有在显著改善端到端证据质量时才值得引入延迟和运维成本。
- **Current Choice**：先测无 reranker baseline；再测试一个通用 reranker。领域训练不属于初始方案。
- **Rationale / Evidence**：当前没有干净的无人机领域对照结果。
- **Validation Method**：固定 candidate set，对比 nDCG/Recall@k、引用正确率、answer correctness、p95 latency 和单位请求成本；仅在置信区间内有稳定净收益时启用。
- **Result**：尚未执行。
- **Affected Artifacts**：RAG retrieval pipeline；Slice 5、6。
