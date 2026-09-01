# DEC-003 — Multi-product Retrieval

- **Status**：OPEN
- **Question**：同时解释多个候选时，证据预算应如何在商品间分配？
- **Context**：全局 top-k 容易被文档量大或语义相似的一款商品占满；固定 per-product quota 可能浪费预算；two-stage 增加延迟与复杂度。
- **Current Choice**：不固定算法。用 global top-k、per-product quota 和先选商品后商品内检索的 two-stage 三组建立对照。
- **Rationale / Evidence**：两个参考项目都没有证明多商品证据覆盖策略。
- **Validation Method**：以二至三款商品的推荐/比较题评估 gold-product coverage、每商品 Evidence Recall、引用归属正确率、答案覆盖、token 与 p95 latency。
- **Result**：尚未执行。
- **Affected Artifacts**：Retriever、Evidence Composer；Slice 6。
