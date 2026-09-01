# DEC-007 — Milvus

- **Status**：OPEN
- **Question**：Milvus 是否是 V1 合适的检索存储？
- **Context**：参考 RAG 项目已有 Milvus hybrid retrieval，但目标数据规模、metadata filtering、部署环境和运维能力尚未验证。Architecture 需要的是可过滤、版本化、可评估的 Retriever，不是特定产品。
- **Current Choice**：Milvus 是 Provisional Design Choice；在建立 corpus 与 retrieval benchmark 前不写成硬依赖。
- **Rationale / Evidence**：复用思路有价值，但参考实现有模块级连接副作用且真实规模未知。
- **Validation Method**：使用实际 corpus 比较候选引擎的 metadata filter 正确性、hybrid 支持、Recall@k、索引/查询延迟、更新删除、备份恢复、开发与运维成本。
- **Result**：尚未执行。
- **Affected Artifacts**：RAG adapter、部署配置；Slice 5。
