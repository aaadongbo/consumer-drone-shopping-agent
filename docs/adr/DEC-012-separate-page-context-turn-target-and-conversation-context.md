# DEC-012 — Separate Page Context, Turn Target, and Conversation Context

- **Status**：PROPOSED / PENDING HUMAN REVIEW / CANDIDATE DECISION
- **Question**：商品页默认对象、用户本轮真正询问的对象与后续代词继承对象是否应共享同一状态？
- **Context**：商品页需要提供低摩擦默认对象，但用户也会临时询问其他商品、发起比较或请求全店推荐。把页面对象永久锁死会忽略显式问题；把每次临时跨产品提问写入长期状态又会污染后续代词与动态事实 scope。
- **Candidate Choice**：三者分离。Page Context 仅提供请求级默认；Turn Target 按“显式 Product / Variant > 已确认 Conversation Context > Page Context > 澄清”解析并约束本轮所有输出；只有明确切换或确认切换后才更新 Conversation Context。比较集合、推荐任务和全站支持意图不是单商品切换。
- **Rationale / Evidence**：该边界同时保留商品页上下文便利性、显式用户意图优先级和长期状态稳定性，并允许 Answer、Card、Evidence、bindings 与动态事实使用同一可审计对象范围。
- **Validation Method**：用商品页代词、临时跨产品、明确切换、确认切换、歧义 Product / Variant、比较、推荐和全站支持 journey matrix 验证目标来源、状态 diff、路由和输出身份；任何默认首项选择、页面事实混入或未确认状态污染均失败。
- **Acceptance Boundary**：只有 Human Review 接受 Slice 3 Planning Baseline 后，本候选决策才可视为 `ACCEPTED`；在此之前不得把它用作已接受的 Product Behavior、Architecture 或 Implementation authority。
- **Result**：待 Human Review；实现验证待 Slice 3。
- **Affected Artifacts**：[PROJECT_SPEC.md](../PROJECT_SPEC.md) 目标解析行为；[ARCHITECTURE.md](../ARCHITECTURE.md) State、Router、TargetResolution、AnswerEnvelope 与 Trace；Slice 3。
