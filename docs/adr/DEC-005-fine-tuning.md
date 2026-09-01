# DEC-005 — Fine-tuning

- **Status**：OPEN
- **Question**：Prompt、规则、Catalog 和 RAG baseline 后是否仍需模型微调？
- **Context**：参考 RAG 项目含 LoRA 流程，但评估集存在高比例答案泄漏，不能证明微调必要或有效。
- **Current Choice**：Fine-tuning 不是 V1 依赖，也不在 baseline 前实施。只有稳定、可归因且无法通过数据/Contract/提示修复的误差才触发实验。
- **Rationale / Evidence**：降低数据治理、模型版本和部署复杂度；避免用训练掩盖系统边界问题。
- **Validation Method**：先完成模块和 E2E error taxonomy；若特定任务有足够无泄漏样本且 baseline 持续不达标，再做相同数据划分下的受控对照，评估质量、泛化、成本和回归。
- **Result**：尚未触发实验。
- **Affected Artifacts**：模型 adapter、Evaluation；潜在 Later scope。
