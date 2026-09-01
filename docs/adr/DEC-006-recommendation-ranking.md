# DEC-006 — Recommendation Ranking

- **Status**：OPEN
- **Question**：通过 HARD eligibility 后，如何根据 SOFT preferences 对候选排序？
- **Context**：V1 的目标是用户适配，不是利润、库存去化或流行度最大化。排序必须可解释、稳定且不能让软分数覆盖硬条件。
- **Current Choice**：使用透明、确定性的软偏好匹配规则作为 baseline；权重和更复杂方法保持开放。
- **Rationale / Evidence**：规则 baseline 最容易审计并支持早期标注；当前没有行为数据支持 learning-to-rank。
- **Validation Method**：建立带偏好强度和成对人工选择的推荐集；评估 hard-violation、pairwise agreement、top-k usefulness、解释一致性、稳定性与无匹配行为。
- **Result**：尚未执行。
- **Affected Artifacts**：Catalog/Constraint Engine、Recommendation output；Slice 2、6。
