# DEC-010 — Deterministic HARD Constraints at Variant Level

- **Status**：ACCEPTED
- **Question**：正式推荐的硬约束资格由模型还是确定性逻辑判断？
- **Context**：预算、重量、功能与可售性直接决定候选合法性；模型自由判断不可稳定复现，也容易混淆 Product/Variant。
- **Current Choice**：HARD eligibility 由 Catalog/Constraint Engine 对具体 Variant 以确定性代码判断；UNKNOWN 不通过对应硬约束。模型可解析表达，但不能覆盖结果。
- **Rationale / Evidence**：这是满足无硬违规、可审计和无跨变体拼接的必要条件。
- **Validation Method**：规则属性测试、边界值和单位测试、unknown/missing fixtures，以及 recommendation E2E hard-violation gate。
- **Result**：设计评审已接受；实现验证待 Slice 2、4、6。
- **Affected Artifacts**：[PROJECT_SPEC.md](../PROJECT_SPEC.md) 筛选行为；Architecture 的 Catalog 与 Recommendation Contract。
