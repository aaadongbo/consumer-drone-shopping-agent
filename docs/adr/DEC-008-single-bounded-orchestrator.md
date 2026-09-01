# DEC-008 — Single Bounded Orchestrator

- **Status**：ACCEPTED
- **Question**：V1 使用单编排器还是开放式 Multi-Agent？
- **Context**：V1 用户旅程有限，正确性依赖稳定状态、工具预算和职责边界；多 Agent 会增加状态一致性、trace 和评估难度。
- **Current Choice**：一个有界 Agent/Router 协调 State、Catalog、Shopify、RAG 和 Composer；不采用自治 Agent 间协商。
- **Rationale / Evidence**：参考对话项目的显式 arbitration 已足以支撑能力路由；目标范围没有需要自治多 Agent 的证据。
- **Validation Method**：通过七个 Vertical Slice 的 journey eval 验证可覆盖性；若未来出现单编排器无法表达的独立权限/生命周期，再开新 Decision。
- **Result**：设计评审已接受；实现验证待各 Slice 完成。
- **Affected Artifacts**：[ARCHITECTURE.md](../ARCHITECTURE.md) Agent/Router 边界；全部 Slice。
