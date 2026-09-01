# DEC-002 — Chunking

- **Status**：OPEN
- **Question**：无人机商品页、FAQ 和手册应采用何种分块策略？
- **Context**：参考 RAG 项目提供标题层级和 parent-child 模式，但语义分组可能改变原文顺序。无人机资料还可能包含规格表、警告、脚注和跨页步骤。
- **Current Choice**：从保持原始顺序和 locator 的 heading-aware overlap baseline 开始；parent-child 与表格感知策略作为实验组。
- **Rationale / Evidence**：可回溯性是硬边界，而最佳块大小取决于真实资料分布。
- **Validation Method**：建立覆盖事实、步骤、限制、表格和跨段问题的数据集；比较 Evidence Recall@k、引用正确率/完整性、上下文 token、重复率和解析失败率。
- **Result**：尚未执行。
- **Affected Artifacts**：RAG ingestion/retrieval；Slice 5、6。
