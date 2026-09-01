# DEC-011 — Protocol-independent Internal Tool Contract

- **Status**：ACCEPTED
- **Question**：内部 Shopify 能力是否直接以 MCP schema 作为领域接口？
- **Context**：MCP 是有用的互操作协议，但参考项目显示 schema/handler 漂移和异常语义不足；目标系统需要稳定 typed data、store scope、freshness 和错误分类。
- **Current Choice**：内部 Tool Contract 与 MCP 解耦；MCP 只在有外部互操作需求时作为 adapter。
- **Rationale / Evidence**：保护领域模块不受传输协议和 SDK 生命周期影响，同时保留未来 MCP 接入能力。
- **Validation Method**：对内部 adapter 和可选 MCP adapter 运行同一组 contract tests，验证数据、错误和只读 allowlist 等价。
- **Result**：设计评审已接受；实现验证待 Slice 1。
- **Affected Artifacts**：[ARCHITECTURE.md](../ARCHITECTURE.md) Shopify Tool Layer；Slice 1。
