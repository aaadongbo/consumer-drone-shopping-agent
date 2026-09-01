# DEC-009 — Dynamic Commerce Facts Separate from RAG

- **Status**：ACCEPTED
- **Question**：价格、库存、可售状态是否可以由文档索引回答？
- **Context**：这些事实随时变化，文档索引具有不可避免的滞后。
- **Current Choice**：动态 commerce 事实由 Shopify 只读 Tool 在回答时按策略获取/刷新；RAG 只承载商家授权的相对静态知识。
- **Rationale / Evidence**：避免陈旧事实误导购买决策，并允许独立的新鲜度与失败语义。
- **Validation Method**：Contract/E2E 测试注入文档与 Shopify 不一致数据，确认动态事实始终采用当前 ToolResult 并披露新鲜度。
- **Result**：设计评审已接受；实现验证待 Slice 1、6、7。
- **Affected Artifacts**：[PROJECT_SPEC.md](../PROJECT_SPEC.md) 动态事实行为；Architecture 的 Shopify/RAG/Evidence 边界。
