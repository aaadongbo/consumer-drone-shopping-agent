# Slice 1 Ordered Implementation Tasks

> 状态：APPROVED / Authorized for T01
>
> 执行设计：[plan.md](./plan.md)
>
> 当前按批准顺序执行 Implementation；T01 已完成，T02 尚未开始。

## 1. Status Model

任务状态仅使用：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`DONE`。

当前状态：

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Bootstrap 最小执行与测试 Harness | DONE | SATISFIED — Human Final Approval |
| T02 | 固化 Slice 1 版本化最小 Contract | NOT_STARTED | T01 |
| T03 | 建立 Shopify Read Port 与 deterministic fixture | NOT_STARTED | T02 |
| T04 | 打通显式 Variant 的应用层 Walking Skeleton | NOT_STARTED | T03 |
| T05 | 收敛 Product / Variant identity 与 ambiguity | NOT_STARTED | T04 |
| T06 | 完成 Tool failure 与标准 fallback 映射 | NOT_STARTED | T04, T05 |
| T07 | 加固 Evidence、动态事实与输出 scope Gate | NOT_STARTED | T04, T05, T06 |
| T08 | 接入薄 Conversation API 与 Minimal E2E Client | NOT_STARTED | T07 |
| T09 | 收敛 Verification Matrix 与 Completion Evidence | NOT_STARTED | T08 |

只允许一个 Task 处于 `IN_PROGRESS`。Task 未满足自身 Acceptance 与 Verification 时不得标为 `DONE`。

## 2. Coding Protocol

### 每个 Task 开始前

1. 重新读取 [plan.md](./plan.md) 与当前 Task。
2. 检查 `git status --short`、当前 diff 与最近 Git history；识别并保护用户已有改动。
3. 确认依赖 Task 已 DONE，并运行与当前边界相关的 baseline。
4. 确认 Scope、Acceptance、验证层级与 Human Escalation 停止条件。
5. 只加载当前 Task 需要的上下文；不得顺手设计或实现后续 Slice。
6. 将当前 Task 标为 `IN_PROGRESS`，记录开始时的 commit / diff 状态。

### 每个 Task 结束时

1. 运行与风险对应的 Static / Unit / Contract / Integration / E2E gate。
2. Review 完整 diff，检查身份、Evidence、只读、安全与 Scope。
3. 检查是否误实现 ConversationState、RAG、推荐、比较、正式 Widget、MCP 或其他后续 Slice。
4. 在本 Task 的 Execution Record 中填写实际命令、exit code、结果摘要与证据位置；不得把预期命令冒充已运行。
5. 记录 Discovery、限制和未完成项；必要时按 plan 的 Reconcile 分类更新 Task / Plan。
6. 保持 repository 可继续工作。全部 Acceptance 满足后才标为 DONE，否则保持 IN_PROGRESS 或按规则 BLOCKED。

## 3. Ordered Change Units

### T01 — Bootstrap 最小执行与测试 Harness

**Goal / Change**

在当前仅含设计文档的仓库中建立 Slice 1 所需的最小可执行后端与分层测试入口，使后续 Task 有稳定的 static/test baseline。只建立真实需要的目录与配置，不预建 Architecture 全部 tree。

**Contract**

- 不定义业务 wire contract；只建立可被后续 contract / unit / integration / e2e 测试使用的运行边界。
- 采用 Architecture 当前 Python/FastAPI design choice 时，可使用直接服务 Slice 1 的最小 Python 项目/test runner、static/type/format 工具、FastAPI 配套 schema validation、最小 HTTP test client、deterministic fixture 与测试辅助库，无需 Human Escalation。依赖必须最小、版本明确、可替换、实际使用且不自动引入大型框架；具体版本在执行时基于当前环境确认并记录。
- 若需要数据库/durable state、Redis、消息系统/任务队列、RAG/向量数据库、Agent Framework、外部托管基础设施、observability platform、影响多个 Slice 的主要生产依赖、改变 Architecture Boundary 的依赖，或真实外部服务作为 CI 前提，则停止并升级。

**Acceptance**

- 最小源代码包可被测试环境导入。
- Static/test runner 能执行一个不含业务语义的 smoke test。
- 测试层可区分 targeted unit/contract、integration 和 e2e，而无需预建空目录树。
- 未实现 API endpoint、Shopify、Contract、RAG、state 或 Widget。

**Verification**

- Static：配置和包导入检查。
- Unit：单个 harness smoke。
- Diff review：只有 bootstrap/test 必需内容，无业务实现。
- 实际命令在执行时根据最终 toolchain 记录，不在此虚构。

**Dependencies**

- SATISFIED — Human Final Approval of Slice 1 plan/tasks。

**Out of Scope**

- 生产部署、容器、服务配置、CI 平台配置、数据库/durable state、Redis、消息/任务系统、RAG/向量库、Agent Framework、托管基础设施、observability platform、真实外部连接、完整 repository tree。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：`7dd2090fcbe2542b7da7ec1fe905b9c34c990044`; none (`git status --short` and `git diff --check` both clean)
- Changed paths：`.python-version`, `.gitignore`, `pyproject.toml`, `uv.lock`, `backend/__init__.py`, `tests/test_harness.py`, `changes/slice-01-product-facts/tasks.md`
- Commands and exit codes：
  - Preflight `git status --short`, `git diff --check`, `git log --oneline -5`, source/Task/Architecture reads: `0`.
  - Initial `uv lock && uv sync --group dev && uv run ruff check . && uv run ruff format --check . && uv run python -c 'import backend; assert backend.__name__ == "backend"' && uv run pytest -m 'unit or contract' -q`: `1`; static/import steps passed, then pytest exposed that the repository root was absent from its import path. Added explicit pytest `pythonpath = ["."]`.
  - Corrected `uv lock --check`, `uv sync --locked --group dev`, `uv run ruff check .`, `uv run ruff format --check .`, package import check, targeted smoke, `pytest --markers`, and `git diff --check`: each `0`; targeted smoke `1 passed`.
  - Python 3.12 alignment `uv python find 3.12`: `0`; final `uv lock && uv sync --locked --group dev`: `0`, using CPython `3.12.13`.
  - Final `uv run python --version`, `uv lock --check`, Ruff lint/format checks, package import check, targeted smoke, pytest collection, and `git diff --check`: each `0`; `1 passed`, `1 test collected`.
  - Post-review task-status correction followed by lock, Ruff lint/format, package import, targeted smoke, `git diff --check`, core Artifact zero-diff check, and staged full-diff review: each `0`; targeted smoke `1 passed`.
- Results / evidence locations：Toolchain and four layer markers in `pyproject.toml`; resolved dependency graph in `uv.lock`; import boundary in `backend/__init__.py`; non-business unit smoke in `tests/test_harness.py`.
- Discoveries / limitations：Pytest 9 required an explicit repository-root import path for this uninstalled minimal package. T01 provides markers for unit/contract, integration, and e2e selection but intentionally adds only one unit smoke; later suites remain unimplemented. Direct development dependencies are only `pytest==9.0.3` and `ruff==0.15.12`; there are no runtime dependencies, API endpoint, business contract, Shopify, state, RAG, Widget, external service, deployment, or CI configuration. FastAPI remains deferred until a task actually uses it.

### T02 — 固化 Slice 1 版本化最小 Contract

**Goal / Change**

以可序列化类型和公共 wire schema 固化 plan 第 8 节真正使用的最小 Contract，使 client、API、application、fixture 与测试共享同一语义。

**Contract**

- TurnRequest、Page Context、ConversationRef。
- ProductRecord、VariantRecord、AttributeValue。
- ToolResult、Minimal RouteDecision、Evidence。
- AnswerEnvelope、Standard Fallback、Minimal Trace event。
- `schema_version` 与明确的 discriminated success/fallback 结构。
- Invalid TurnRequest 的 transport validation boundary；它不是 AnswerEnvelope fallback，具体 HTTP status/minimal body 在执行时决定并记录。

**Acceptance**

- 有效 TurnRequest / AnswerEnvelope 通过 schema validation；缺必填 scope、非法 enum、UNKNOWN 携带假值等失败。
- 无效 TurnRequest 的 contract 明确要求 transport rejection，且不能进入 application、QuestionInterpreter 或 Shopify；validation response 稳定且不泄漏内部异常。
- `state_revision` 未被实现为状态机制；stream event 未定义。
- Answer 和 Fallback 可明确区分；reason codes 与 plan 一致。
- Client/API 预期消费同一份 schema，不复制第二套 DTO。
- Contract 不预加推荐、比较、constraints、RAG 或完整 state 字段。
- Schema validation 所需的 FastAPI 直接配套最小依赖不触发升级；具体库版本此处不预先锁定。影响多个 Slice或改变 Architecture Boundary 的主要依赖必须升级。

**Verification**

- Static：类型/格式检查。
- Contract：valid/invalid serialization、版本、enum、required/optional、UNKNOWN invariant、fallback shape。

**Dependencies**

- T01。

**Out of Scope**

- 完整 API Error Framework、业务路由、adapter、自然语言生成、持久化、stream transport、主要跨 Slice 生产依赖。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

### T03 — 建立 Shopify Read Port 与 deterministic fixture

**Goal / Change**

实现协议无关、无写 surface 的 Shopify Read Port Slice 子集，以及可为成功、UNKNOWN、not-found、partial 和外部错误提供确定性结果的 fixture adapter。

**Contract**

- Read operations 仅 `get_products`、`get_variants`、`refresh_commerce_state`。
- ToolResult 保留 typed data、status、source、observed_at、error_code、retryable 和 partial missing fields。
- Fixture call ledger 记录 safe operation/scope 和 read/write 分类。

**Acceptance**

- Fixture 至少包含两个 Product、一个 Product 下两个差异 Variant、共享/Variant-specific/UNKNOWN/dynamic facts。
- 固定 observed_at 可注入并原样返回。
- Product/Variant not found、timeout、rate limit、auth、partial 均为可判别 ToolResult。
- Port 不提供 write 方法；unknown/write probes 被 allowlist 拒绝。
- Contract tests 的 write-call count 为 0。

**Verification**

- Static：Port public surface inspection。
- Unit：fixture lookup、identity ownership、fixed clock、error injection。
- Contract：各 ToolResult 分支、allowlist 与 zero-write ledger。

**Dependencies**

- T02。

**Out of Scope**

- 真实 Shopify、Admin/Storefront credentials、pagination/retry production policy、search_products、缓存、MCP。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

### T04 — 打通显式 Variant 的应用层 Walking Skeleton

**Goal / Change**

以一个已知 Variant 字段 happy path 贯通 Page Context、deterministic QuestionInterpreter、PRODUCT_QA RouteDecision、read port、ToolResult、Evidence、AnswerEnvelope 和相关 trace。先证明纵向闭环，不同时完成所有失败分支。

**Contract**

- 输入：有效 TurnRequest，含 P1/V1 页面 scope 和 fixture 可识别的字段问题。
- 输出：同步 ANSWER Envelope，含 resolved P1/V1、Evidence、claim binding、correlation ID；minimal Product Card 可省略。
- Trace：至少包含 request、context、route、tool call/result、evidence、answer 事件。

**Acceptance**

- 应用层 integration test 对显式 Variant 已知字段稳定 PASS。
- Answer、Evidence 与 binding 全为同一 store/product/variant；Card 省略合法，若存在也必须为同一 scope。
- Answer claim 的值只取自 ToolResult；每个关键 claim 有 Evidence。
- 所有事件共享 correlation ID；fixture ledger 只有 read call。
- 没有完整 Agent loop、自由工具选择或模型事实生成。

**Verification**

- Unit：deterministic field interpretation 与最小 route。
- Integration：Matrix #1 happy path 和基础 trace correlation。
- Contract：生成 Envelope 再经公共 wire schema validation。

**Dependencies**

- T03。

**Out of Scope**

- Product-only、全部 fallback、API transport、真实模型、正式自然语言质量。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

### T05 — 收敛 Product / Variant identity 与 ambiguity

**Goal / Change**

补齐 Product-only 共享事实、Variant ownership 验证和 Variant-specific ambiguity，确保系统不会默认选 Variant 或跨 Variant 拼接。

**Contract**

- field scope classification：Product-shared / Variant-specific / Dynamic Variant。
- resolved scope 必须验证 `variant_id` 属于 `store_id + product_id`。
- Product-only + Variant-specific 统一返回 `VARIANT_REQUIRED`。

**Acceptance**

- Matrix #2 Product shared fact 返回 Product-scope Evidence。
- Matrix #3 返回 `VARIANT_REQUIRED` 且没有事实 claim。
- Matrix #4/#5 正确区分 Product/Variant not found。
- Foreign Variant 不会在其他 Product 中被搜索并替换。
- Fixture 的差异值证明 price/inventory/bundle/attributes 不跨 Variant 混合。

**Verification**

- Unit：field scope、inherit-only-shared、variant ownership、no-default-selection。
- Integration/E2E at application boundary：Matrix #2～#5。

**Dependencies**

- T04。

**Out of Scope**

- 推荐中的 Variant 代选、比较、Catalog eligibility、商品搜索。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

### T06 — 完成 Tool failure 与标准 fallback 映射

**Goal / Change**

把 UNKNOWN、tool errors、partial 和 out-of-scope 路由为稳定、用户可理解且可行动的 Standard Fallback，不把空数据、失败或旧值包装成事实。

**Contract**

- 覆盖 `FACT_UNKNOWN_OR_MISSING`、`TOOL_TIMEOUT`、`TOOL_RATE_LIMITED`、`TOOL_UNAUTHORIZED`、`TOOL_PARTIAL_RESULT`、`OUT_OF_SCOPE`。
- 每个 fallback 均有 `message/retryable/next_actions`，并通过公共 Envelope schema。

**Acceptance**

- Matrix #6～#10、#15 的 reason code、retryable 与 action 精确匹配 plan。
- UNKNOWN 文案不表达“不支持”、false、0 或确定事实。
- Timeout/rate limit/auth/partial 不读取备用 fixture 值或旧 trace。
- OUT_OF_SCOPE 不调用 Shopify；无开放式 Agent fallback。
- 每条 fallback 有同一 turn correlation ID。

**Verification**

- Unit：ToolResult-to-fallback mapping、UNKNOWN wording invariant、out-of-scope no-call。
- Contract：所有 fallback shape 与 reason code。
- Integration：deterministic failure injection。

**Dependencies**

- T04、T05。

**Out of Scope**

- 自动重试、backoff、人工工单、推荐/法规回答、完整 fallback taxonomy。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

### T07 — 加固 Evidence、动态事实与输出 scope Gate

**Goal / Change**

在 Composer 边界加入 fail-closed 校验，拒绝错 store/product/variant Evidence、存在的 Card 与 Answer scope 错配、binding/output inconsistency 和缺 `observed_at` 的动态事实，并完成最小 trace 脱敏。

**Contract**

- Evidence 与 resolved answer scope 一致；Product-level Evidence 不能支持 Variant-only claim，反之亦然。
- Dynamic ToolResult -> Evidence -> Answer freshness 全链携带 observed_at。
- Composer guard 在内部 trace 输出具体 diagnostic：`EVIDENCE_SCOPE_MISMATCH`、`OUTPUT_SCOPE_MISMATCH` 或 `DYNAMIC_FACT_FRESHNESS_MISSING`；公开 Envelope 统一输出 `INTERNAL_CONSISTENCY_ERROR`，`retryable=false`。
- 公开 fallback 不包含内部对象、stack、schema 或调试信息；Product Card 缺失不触发 guard。
- Trace 只记录 allowlisted safe fields。

**Acceptance**

- Matrix #11～#14 均 fail closed，不返回事实 ANSWER；公开只返回 `INTERNAL_CONSISTENCY_ERROR`，内部 trace 保留对应具体 diagnostic 且不得静默吞掉。
- Product Card 省略时合法；仅在 Card 存在且身份不一致时触发 `OUTPUT_SCOPE_MISMATCH` internal diagnostic。
- 每个成功关键 claim 有存在且 scope-compatible 的 binding。
- 动态值只来自当前 ToolResult，observed_at 一致传播。
- Trace 敏感值 negative tests 通过；没有 raw headers/config dump。

**Verification**

- Unit：product/variant/store mismatch、card mismatch、missing binding、missing freshness、sanitizer。
- Contract：非法 Envelope 无法作为有效 ANSWER 输出；internal diagnostic 不进入 public reason-code enum。
- Integration：动态 current-read precedence 与 fallback。

**Dependencies**

- T04、T05、T06。

**Out of Scope**

- 文档 Evidence、Derived Evidence、RAG citation、全局 TTL、生产 observability backend。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

### T08 — 接入薄 Conversation API 与 Minimal E2E Client

**Goal / Change**

将已验证应用服务暴露为薄 Conversation API，并让 Minimal Client / E2E Harness 使用同一 TurnRequest / AnswerEnvelope wire schema 完成同步请求响应。

**Contract**

- API 入口校验 `schema_version`、ConversationRef、page context 与 user text。
- API 只协调应用服务并返回公共 AnswerEnvelope；不复制领域 DTO 或判断。
- Minimal Client 直接序列化/验证公共 Contract。
- Invalid TurnRequest 在 transport boundary 返回稳定、安全的 validation response，不生成 AnswerEnvelope；具体 HTTP status/minimal body 在 T02/T08 执行时决定并记录。

**Acceptance**

- 显式 Variant happy path 通过 transport-level E2E。
- 至少 Product-only shared、Variant-required、not-found、UNKNOWN、一个 tool error、scope mismatch 和 out-of-scope 通过 E2E。
- 无效 wire input 被稳定拒绝，不进入 application service，不调用 QuestionInterpreter 或 Shopify adapter，也不生成业务 AnswerEnvelope fallback；响应不泄漏内部异常。
- Minimal Client 使用公共 wire schema，测试不得通过手工 payload helper 绕过 validation。
- 成功 Envelope 的 Product Card 可省略；若存在则与 resolved scope、Evidence 和 bindings 一致。
- 返回 Envelope 再次通过公共 schema；correlation ID 可串联 transport 与 application trace。
- E2E ledger write-call count = 0。

**Verification**

- Contract：request/response schema compatibility、invalid input transport rejection、下游 call count=0。
- Integration：API -> application -> fixture。
- E2E：Minimal Client -> API -> final Envelope/fallback。

**Dependencies**

- T07。

**Out of Scope**

- 完整 API Error Framework、正式 Widget、SSE/WebSocket/chunking、浏览器 UI、生产 server/deployment、真实 Shopify/model。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

### T09 — 收敛 Verification Matrix 与 Completion Evidence

**Goal / Change**

补齐 plan Verification Matrix 的全部 19 个 completion gates，执行分层 suite、diff/scope review，并把可复现的实际证据记录到本文件。

**Contract**

- 不新增产品行为；只补足既定 Acceptance 的测试覆盖与必要的局部修正。
- 任何暴露核心语义缺口的修正先按 Reconcile 分类；不得用放宽断言使测试通过。

**Acceptance**

- Matrix #1～#19 全部 PASS，且每项能定位到具体测试结果。
- Static、Unit、Contract、Integration、E2E 的最终 gates 全部成功。
- 完整 suite 的 Shopify write-call count = 0。
- Trace correlation 与敏感信息 negative tests 成功。
- Internal diagnostics 均保留在 trace、只公开映射为 `INTERNAL_CONSISTENCY_ERROR`，且公开 fallback 无内部细节；invalid wire input 停在 transport boundary、下游 call count=0。
- Final diff review 未包含 Non-goals；核心 Artifact 未经授权无修改。
- Optional live smoke 明确标为未运行或单独授权结果，不阻塞完成。
- Completion checklist 全部勾选并记录实际命令、exit code 与结果位置。

**Verification**

- Static + full targeted Unit/Contract。
- Integration walking skeleton suite。
- E2E full Matrix。
- Git diff / scope / secret review。

**Dependencies**

- T08。

**Out of Scope**

- 新能力、性能平台、真实外部服务、Slice 2～7、为了“完善”而重构无关模块。

**Execution Record（执行后填写）**

- Start commit / pre-existing diff：TBD
- Changed paths：TBD
- Commands and exit codes：TBD
- Results / evidence locations：TBD
- Discoveries / limitations：TBD

## 4. Dependency Flow

```text
Human Review
  -> T01 Bootstrap
  -> T02 Contracts
  -> T03 Read Port + Fixture
  -> T04 Application Walking Skeleton
  -> T05 Identity / Ambiguity
  -> T06 Failure Mapping
  -> T07 Evidence / Freshness / Scope Guards
  -> T08 Thin API + Minimal Client E2E
  -> T09 Matrix Closure + Completion Evidence
```

T04 尽早形成应用层纵向闭环；T05～T07 在该闭环上增加明确失败原因；T08 最后增加薄 transport，避免先横向建设完整 API 或框架。

## 5. Blocking Record

当前无 blocker。若触发 [plan.md](./plan.md) 的 Human Escalation Conditions，在此记录：

- Discovery：TBD
- Evidence：TBD
- Impact：TBD
- Options：TBD
- Recommendation：TBD
- Blocked work：TBD

不得仅因工作复杂或测试失败将任务标为 BLOCKED；先完成安全、范围内的诊断与 Reconcile。

## 6. Slice Completion Checklist

- [ ] T01～T09 均为 DONE，且无跳过的 Acceptance。
- [ ] Matrix #1～#19 全部 PASS，并有结果定位。
- [ ] TurnRequest / AnswerEnvelope 使用同一公共版本化 contract set，各自通过对应 wire schema。
- [ ] 无效 TurnRequest 在 transport boundary 被稳定、安全地拒绝；不产生 AnswerEnvelope，不调用 application、QuestionInterpreter 或 Shopify。
- [ ] 显式 Variant、Product shared 与 Variant ambiguity 行为正确。
- [ ] Product Card 可省略；若存在，与 Answer resolved scope、Product / Variant、Evidence 和 binding 无 scope 混淆。
- [ ] Dynamic facts 来自当前 ToolResult 且保留 observed_at。
- [ ] UNKNOWN、timeout、rate limit、auth、partial、not-found 和 out-of-scope 均有正确 fallback。
- [ ] Scope/binding/output/freshness 完整性失败不返回事实 ANSWER；internal diagnostic 留在 trace，对外仅为安全的 `INTERNAL_CONSISTENCY_ERROR`。
- [ ] 无 Evidence 不生成商品事实结论。
- [ ] 完整 Turn trace 可由 correlation ID 关联。
- [ ] Trace 不含 token、secret、credential 或敏感配置。
- [ ] Shopify Port 无写 surface；Contract、Integration、E2E write-call count 均为 0。
- [ ] Final diff 未实现完整 state、MongoDB、Redis、RAG、Milvus、推荐、比较、正式 Widget、MCP、Skill 或后续 Slice。
- [ ] 四个核心 Artifact 未被意外修改；若有授权 Reconcile，Decision 与证据完整。
- [ ] 实际验证命令、exit code、结果摘要和限制已写入各 Task Execution Record。
- [ ] Optional live smoke 的运行状态被明确记录，且未成为 CI 唯一依赖。
- [ ] Human Review 接受 Completion Evidence 后，才进入下一 Slice planning。

## 7. Recommended Next Task

**T01 — Bootstrap 最小执行与测试 Harness** 已完成。Human Review 通过并提交 T01 后，从 **T02 — 固化 Slice 1 版本化最小 Contract** 开始；T02 当前保持 `NOT_STARTED`。
