# DEC-001 — Query Rewrite

- **Status**：OPEN
- **Question**：哪些承接、省略、指代或长对话场景需要 Query Rewrite？
- **Context**：参考对话项目在主链中普遍 rewrite，但商品名称、数值、单位、否定和 HARD/SOFT 语义一旦被改写错误，会污染状态与检索。原始用户文本必须始终保留。
- **Current Choice**：V1 baseline 默认不 rewrite。实验候选为仅在明确的指代消解或检索失败条件下产生辅助查询；辅助查询不得覆盖原文或直接修改 ConversationState。
- **Rationale / Evidence**：参考项目证明 rewrite 可改善上下文承接，但没有商品约束保真证据；目标风险高于一般 FAQ。
- **Validation Method**：构建含型号、预算、单位、否定、撤回、代词和跨轮省略的标注集，对比 off、always-on、gated 三组；测量约束保真、实体保持、retrieval recall、最终回答正确率和额外延迟。
- **Result**：尚未执行。
- **Affected Artifacts**：Architecture 的 State、Router、RAG 输入；Slice 3、5、6。
