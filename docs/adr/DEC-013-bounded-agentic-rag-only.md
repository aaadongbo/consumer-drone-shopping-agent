# DEC-013 — Bounded Agentic RAG Only

- **Status**：ACCEPTED
- **Question**：V1 的 Product RAG 与多商品推荐是否允许 Agentic 多步工具循环？
- **Context**：Product RAG 可能需要一次同商品定向补检；Evidence-based Recommendation 还可能需要动态 commerce refresh 或 Derived Evidence 复算，尤其在候选解释不完整或硬条件依赖多个来源时。开放式 ReAct、多 Agent 自治或开放网络检索会扩大身份、证据和工具边界，难以保证 Shopify 只读、商品范围过滤和可复现评估。
- **Decision**：采用单编排器内的受限 ActionPlan。每轮必须绑定 Turn Target、约束、候选集合、allowlist 和预算；`max_action_rounds = 2 total`，第 1 轮包含初始检索/读取，最多再执行一轮纠正。Action type 可包括同一 Product/Variant 定向二次检索、`refresh_commerce_state`、Derived Evidence 复算/HARD 复核和请求澄清；其中 Slice 5 只执行定向 Product RAG 检索或澄清，commerce refresh、Derived Evidence 和 HARD recheck 的执行推迟到 Slice 6。Evidence Gate 最终决定能否回答。
- **Rationale / Evidence**：该方案给 Product RAG 和 Evidence-based Recommendation 留出必要补证空间，同时保持 DEC-008 的单编排器、DEC-009 的动态/静态分层、DEC-010 的确定性 HARD eligibility 和 DEC-011 的协议无关工具边界。
- **Validation Method**：Slice 5 用文档摄取、检索、补检和 claim coverage matrix 验证；Slice 6 用多候选推荐、Derived Evidence、动态刷新和降级 matrix 验证。任何预算耗尽、证据错配、越界检索、动态事实从文档回答或硬条件被模型放宽均失败。
- **Acceptance Boundary**：Human 已接受 Slice 5 的 Goal、Scope、Acceptance 和本决策。该架构决策不构成 Slice 5 Implementation authority；仍须建立 Slice 5 planning baseline、激活 workflow policy，并获得相应执行授权。
- **Result**：Human Decision 已接受；实现验证待 Slice 5 和 Slice 6。
- **Affected Artifacts**：[PROJECT_SPEC.md](../PROJECT_SPEC.md) Product RAG / Recommendation 行为；[ARCHITECTURE.md](../ARCHITECTURE.md) Product RAG、Agent/Router、Evidence Composer 与 Trace；Slice 5、6。
