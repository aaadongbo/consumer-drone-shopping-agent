# Slice 5 Ordered Implementation Tasks — Product RAG

> 状态：IMPLEMENTATION AUTHORIZED / Formal Slice task table
>
> Human 已接受 Slice 5 的 Goal、Scope、Acceptance 及 bounded Agentic RAG 决策；planning baseline 与 S05 Workflow Policy 已集成。以下任务使用正式 workflow Task state（`NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` / `DONE`），按依赖和任务表顺序执行。

Slice 5 只实现单一 Store/Product/optional Variant 范围内的 Product RAG、Evidence Gate、同商品定向补检和澄清。`refresh_commerce_state`、Derived Evidence 复算和 HARD eligibility recheck 可作为全局 action type 被文档命名，但不在 Slice 5 执行；它们由 Slice 6 承接。

Provisional budget config:

| Key | Provisional hard limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |

`max_action_rounds = 2 total` means round 1 is baseline retrieval; only one corrective round is allowed.

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Document manifest and ingestion contract | DONE | Slice 4 completion + Slice 5 planning approval |
| T02 | Scoped chunking and locator baseline | DONE | T01 |
| T03 | Metadata-filtered baseline retrieval | DONE | T02 |
| T04 | Evidence quality and claim coverage gate | DONE | T03 |
| T05 | Bounded Product RAG action loop | DONE | T04 |
| T06 | Product RAG answer/fallback walking skeleton | NOT_STARTED | T05 |
| T07 | Slice 5 evaluation matrix and completion evidence | NOT_STARTED | T06 |

## T01 — Document manifest and ingestion contract

- **Goal**：定义授权文档、版本、source locator、store/product/variant metadata 和 ingestion manifest。
- **Why**：RAG 只有在来源、授权、版本和 locator 可审计时，后续 Evidence 才能被用户和测试回放。
- **Scope**：未来 `backend/rag/` 的 manifest/value object；`eval/datasets/` 的最小授权文档 fixture；unit/contract tests。
- **Contract**：`DocumentSource`、source authorization state、version、canonical locator、store/product/optional variant metadata。
- **Acceptance**：未授权来源被拒绝；每个 chunk 可回到 source/version/locator；不导入真实秘密、客户数据或开放网络内容。
- **Verification**：Static + Unit + Contract.
- **Dependencies**：Slice 4 completion + Slice 5 planning approval.
- **Out of Scope**：真实托管向量库、开放网络、LLM 清洗替代原文、生产文档导入。

Execution Record:

- Start commit: `ca34262a94b9e89b2670833371a7b0a764d905b1`.
- Implemented internal `backend/rag` manifest value objects, canonical `rag://` source locators, authorized-source manifest validation, and a deterministic authorized product-doc fixture under `eval/datasets/`.
- Added unit and contract coverage for authorized single-product scope, locator replay, strict field validation, unauthorized source rejection, scope/version mismatch rejection, and absence of secret/customer/open-network payloads.
- First targeted run failed because one test used `model_copy()` as if it revalidated Pydantic invariants, and another expected `ValidationError` for an explicit `ValueError`; both tests were corrected without broadening implementation scope.
- Verification: targeted `pytest tests/unit/test_s05_t01_document_manifest.py tests/contract/test_s05_t01_ingestion_contract.py -q` passed with `8 passed`; targeted Ruff lint and format checks passed.
- Dependency, public Contract, Architecture, Workflow, Shopify, external service, and open-network changes: none.

## T02 — Scoped chunking and locator baseline

- **Goal**：建立保序、可定位、heading-aware 的 baseline chunking。
- **Why**：FAQ、包装清单、手册步骤和政策片段需要稳定 locator，否则 answer citation 和冲突排查不可复现。
- **Scope**：未来 `backend/rag/` chunking utilities；golden source fixtures；unit tests。
- **Contract**：`DocumentChunk` 包含 source identity、chunk_id、ordered locator、heading path、text、metadata filter fields。
- **Acceptance**：标题、表格/列表、页/段 locator 保留；重复、删除和失效源可追踪；chunk metadata 不丢 store/product/variant。
- **Verification**：Unit + golden source fixtures.
- **Dependencies**：T01.
- **Out of Scope**：semantic chunking 固化、训练数据生成、reranker、索引引擎选择。

Execution Record:

- Start commit: `fc60c917d9e53c8b41b9ede8989737815a568568`.
- Implemented internal `DocumentChunk`, deterministic `chunk_manifest()` and `chunk_document_source()` helpers with stable ordering, canonical source locators, heading paths, and source metadata propagation.
- Added unit coverage for scope/source/version preservation, deterministic fresh values, heading boundaries, list/table row grouping, and locator identity validation.
- First targeted test run passed; first Ruff run reported import/line-length formatting issues in the new T02 test file, then the test text fixtures were split and formatting passed.
- Verification: targeted `pytest tests/unit/test_s05_t02_chunking.py -q` passed with `5 passed`; targeted Ruff lint and format checks passed.
- Semantic chunking, training-data generation, reranker, retrieval engine selection, public Contract, Architecture, Workflow, dependency and external-service changes: none.

## T03 — Metadata-filtered baseline retrieval

- **Goal**：实现按单一 Turn Target 强制过滤的 baseline retrieval。
- **Why**：Slice 5 的核心风险是把其他商品文档当成当前商品证据；metadata filter 必须先于 ranking。
- **Scope**：未来 `backend/rag/` retriever port/fixture；integration tests with local index fixtures；retrieval eval baseline。
- **Contract**：`RetrievalRequest`、`RetrievalResult`、metadata filter、index version、missing/filtered reason。
- **Acceptance**：store/product/variant filter 先于 ranking；不跨商品返回 Evidence；top-k 可复现；错误 product injection 被拒绝。
- **Verification**：Unit + Integration + retrieval eval baseline.
- **Dependencies**：T02.
- **Out of Scope**：multi-product retrieval quota、Milvus 硬依赖、reranker 固化、开放网络检索。

Execution Record:

- Start commit: `d28386ad2dd6508ced7d9fc404acb6f663f60ac5`.
- Implemented internal `RetrievalRequest`, `RetrievalResult`, `RetrievalStrategy`, and deterministic `InMemoryProductRetriever`.
- Retrieval applies store/product/optional variant metadata filtering before ranking and returns scoped `DocumentChunk` evidence with index version and missing reason.
- Added unit and integration coverage for known static retrieval, metadata filter before ranking, cross-product rejection, product-shared chunks under a variant target, and scoped fixture retrieval for FAQ/package/manual/policy questions.
- First restored draft test run passed, then Ruff found two line-length formatting issues in T03 tests; formatting fixed them and targeted tests still passed.
- Verification: targeted `pytest tests/unit/test_s05_t03_retrieval.py tests/integration/test_s05_t03_retrieval_scope.py -q` passed with `8 passed`; targeted Ruff lint and format checks passed.
- Multi-product retrieval quota, Milvus dependency, reranker, open network, public Contract, Architecture, Workflow, dependency and external-service changes: none.

## T04 — Evidence quality and claim coverage gate

- **Goal**：在回答前验证 scope、locator、version、coverage 和 conflict。
- **Why**：RAG 检索命中并不等于事实可回答；claim 必须被正确商品范围内的 Evidence 覆盖。
- **Scope**：未来 `backend/evidence/` quality/coverage checks；`backend/rag/` result adapters；contract/integration tests。
- **Contract**：`EvidenceQuality`、claim coverage、conflict state、`RagFallback`。
- **Acceptance**：claim 无支持证据则删除/降级/fallback；动态事实不由 RAG 放行；冲突或 stale version 不生成确定结论。
- **Verification**：Contract + Integration.
- **Dependencies**：T03.
- **Out of Scope**：推荐排序、自然语言文案优化、commerce refresh、Derived Evidence。

Execution Record:

- Start commit: `410a8f5fbd52014adeb12cc3f06aa99c20c02f8f`.
- Implemented the internal, lossless `RetrievalEvidenceBundle` adapter and a fail-closed RAG Evidence Gate. It accepts only a verbatim static claim supported by the requested Store/Product/Variant scope, canonical locator and current document version.
- Added typed internal `EvidenceQuality`, `RagClaim`, and `RagFallback` outcomes. Price, inventory and availability always return `DYNAMIC_FACT_REQUIRED`; missing support, foreign scope, stale source versions and conflicting locator content never produce an accepted claim.
- Added focused contract and integration coverage for adapter round-trip, strict accepted-quality shape, dynamic-fact rejection, stale/conflicting sources, exact scoped support, injected foreign product evidence and unsupported text.
- First direct verification could not initialize the sandboxed shared uv cache; the same command was rerun with an isolated temporary cache. The first test pass also exposed an invalid stale-chunk fixture that the lossless adapter correctly rejected before the gate; the fixture was rebuilt as a valid older document version, then the gate assertion passed. Ruff fixed import and formatting diagnostics without semantic change.
- Verification: `pytest tests/contract/test_s05_t04_evidence_gate_contract.py tests/integration/test_s05_t04_evidence_quality.py -q` passed with `8 passed`; targeted Ruff lint/format, `git diff --check`, and `check_scope.py S05-T04` passed.
- Public Contract, Architecture, Workflow, dependency, external-service, commerce refresh, Derived Evidence, HARD recheck and Shopify-write changes: none.

## T05 — Bounded Product RAG action loop

- **Goal**：允许最多 `2` 个 action rounds total：baseline retrieval 后最多一次同商品定向补检或澄清。
- **Why**：Product RAG 需要一个小的补证闭环，但不能滑向开放式 ReAct 或跨模块推荐编排。
- **Scope**：未来 `backend/agent/` bounded loop；`backend/rag/` targeted retrieval call；ActionRoundTrace；unit/integration tests。
- **Contract**：`ActionPlan`、`ActionRoundTrace`、budget config、stop reasons。
- **Acceptance**：只执行同一 Store/Product/Variant 定向二次检索或澄清；预算耗尽 fail closed；不执行 `refresh_commerce_state`、Derived Evidence 或 HARD recheck。
- **Verification**：Unit state table + Integration trace.
- **Dependencies**：T04.
- **Out of Scope**：无限 ReAct、多 Agent、开放工具 dispatcher、commerce refresh、Derived Evidence、HARD eligibility recheck。

Execution Record:

- Start commit: `f9594ec521c074448a9ec74a0fb92b4ecdba406a`.
- Implemented an internal `BoundedProductRagLoop`: one baseline retrieval plus at most one same-target targeted retrieval or clarification action. Its strict `ProductRagBudget` keeps the approved limits at two rounds/two tool calls, 8s, 4k retrieval tokens and 1.2k model tokens.
- Added replayable `ActionPlan`, `ActionRoundTrace`, observation, verification and budget-consumption models. The loop accepts no generic operation and only calls a typed RAG `retrieve()` capability; it cannot mutate Store/Product/Variant scope.
- Integrated the T04 Evidence Gate. Dynamic facts stop as `DYNAMIC_FACT_REQUIRED`; deadline and retrieval-token exhaustion downgrade otherwise accepted evidence to `BUDGET_EXHAUSTED`, so a later answer layer cannot expose it.
- Initial targeted tests exposed two trace/safety defects: the baseline trace was omitted when a second retrieval ran, and token-budget exhaustion retained accepted evidence. Both were fixed before the passing rerun. One import-order diagnostic was automatically fixed by Ruff.
- Verification: `pytest tests/unit/test_s05_t05_bounded_rag_loop.py tests/integration/test_s05_t05_rag_loop.py -q` passed with `9 passed`; targeted Ruff lint/format, `git diff --check`, and `check_scope.py S05-T05` passed.
- Public Contract, Architecture, Workflow, dependency, external-service, commerce refresh, Derived Evidence, HARD recheck and Shopify-write changes: none.

## T06 — Product RAG answer/fallback walking skeleton

- **Goal**：打通 Product QA 的 RAG Evidence -> Answer/Fallback 闭环。
- **Why**：在 Slice 5 结束前需要一个真实 walking skeleton，证明检索、证据、trace 和回答绑定能协同工作。
- **Scope**：未来 `backend/application/` Product QA flow；`backend/rag/` retriever；`backend/evidence/` gate；contract/integration/e2e tests。
- **Contract**：现有 `AnswerEnvelope`、Evidence binding、`RagFallback`、ActionRoundTrace。
- **Acceptance**：FAQ/包装/手册/政策 happy path 与缺证 fallback 均通过；Answer/Evidence/Trace 绑定同一 Turn Target；动态事实请求不由文档回答。
- **Verification**：Contract + Integration + E2E.
- **Dependencies**：T05.
- **Out of Scope**：多商品推荐、比较表、正式 Widget、真实外部服务、Slice 6 recommendation。

## T07 — Slice 5 evaluation matrix and completion evidence

- **Goal**：覆盖 S5-A01～S5-A12 和 Matrix #1～#12。
- **Why**：完成 Slice 5 前需要证明单商品 RAG 没有跨商品、动态事实、预算和证据绑定漏洞。
- **Scope**：tests、eval fixtures、tasks execution evidence。
- **Contract**：Slice 5 acceptance matrix、budget stop reasons、ActionRoundTrace replay evidence。
- **Acceptance**：full suite、scope、secret、zero-write、dynamic/static split、budget limit 和 Evidence Gate 通过。
- **Verification**：Static + Unit + Contract + Integration + E2E + full suite.
- **Dependencies**：T06.
- **Out of Scope**：Slice 6 implementation、fine-tuning、push、feature delivery workflow changes。

## Human Escalation

公共 Contract、Product Behavior、Architecture、主要依赖、外部服务、检索引擎锁定、开放网络、超过 `2` 个 total action rounds、跨商品检索、在 Slice 5 执行 commerce refresh / Derived Evidence / HARD recheck、Shopify write 或 Evidence Gate 放宽都必须升级。
