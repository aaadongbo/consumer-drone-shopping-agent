# Slice 5 Planning — Product RAG with Bounded Evidence Loop

> 状态：APPROVED / Non-executable pending workflow policy and implementation authority
>
> Human 已接受 Slice 5 的 Goal、Scope、Acceptance 及 DEC-013。它仍不授权 Implementation、Task 状态推进、snapshot、commit、push 或外部服务配置。正式进入 Slice 5 前，必须完成 planning baseline、workflow policy 激活和单独 Implementation authority。

## 1. Goal

建立只在单一 Turn Target 范围内工作的 Product RAG：摄取商家授权文档，按一个 store/product/optional variant 与文档版本检索可定位 Evidence，并允许 `max_action_rounds = 2 total` 的受限 ActionPlan。第 1 轮包含 baseline 初始检索；最多再执行一轮同商品定向补检或澄清。最终 Answer 只能表达通过 Evidence Gate 的 claim；资料不足、动态事实、范围错配或预算耗尽必须 fallback。

## 2. Scope

In scope:

- 商家授权资料的最小 ingestion manifest、document version、source locator 和 metadata schema。
- Baseline retriever：store/product/variant metadata filter 优先，返回 Evidence 而不是答案。
- Bounded ActionPlan：`max_action_rounds = 2 total`，其中第 1 轮是 baseline retrieval，最多第 2 轮 corrective action。
- Slice 5 可执行 action：同一 Store/Product/Variant 定向二次检索、请求澄清。
- 全局 action type 可命名 `refresh_commerce_state`、Derived Evidence 二次计算与 HARD 复核，但 Slice 5 不执行；它们推迟到 Slice 6。
- Provisional budget config and exact stop reasons:

| Key | Provisional hard limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |
- Evidence scope、quality、freshness、claim coverage 与 trace。
- 覆盖包装清单、FAQ、手册步骤、使用限制和政策片段的最小 eval/golden set。

Out of scope:

- 多产品推荐执行、跨商品检索、动态 price/inventory/availability 文档回答。
- Shopify commerce refresh、Derived Evidence 复算、HARD eligibility recheck 的执行。
- 开放网络、外部评论、未经商家授权资料、真实 Shopify write、购物车/订单/客户能力。
- 无限 ReAct、多 Agent 自治、Agent Framework、fine-tuning、领域 reranker 固化。
- Milvus 或托管向量库硬依赖；真实外部服务不得成为本 Slice completion gate。

## 3. Product Behavior

- Product RAG 必须以 Slice 3 的 Turn Target 为检索边界。
- 用户问静态说明、FAQ、包装内容、操作或适用政策时，RAG 可以回答；价格、库存、可售状态必须转给 Shopify 只读动态事实路径。
- 若第一轮 Evidence 不足，ActionPlan 可选择一个有理由的同商品补检或澄清动作，但不得改变 Store/Product/Variant identity、跨商品检索或放宽 HARD 约束。
- 每个关键 claim 必须绑定支持它的 Evidence；证据无法覆盖的 claim 必须删除、降级或 fallback。
- 同一 Turn 的 trace 必须记录 target、query、metadata filter、retrieved evidence、ActionRoundTrace、budget、Evidence Gate 和最终输出。
- 预算耗尽时必须立即停止补证，使用对应 stop reason 进入 fallback；不得调用更多工具、扩大检索范围或使用模型常识补齐。

## 4. Minimal Contracts

Planning-level concepts only; public wire schema changes require a later Human checkpoint.

- `DocumentSource`: store_id, product_id, optional variant_id, source_id, source_type, version, canonical locator, authorization state.
- `DocumentChunk`: source identity, chunk_id, ordered locator, heading path, text, metadata filter fields.
- `RetrievalRequest`: turn_target, question, field/intent hint, k, metadata filter, budget.
- `RetrievalResult`: ranked Evidence candidates, retrieval strategy, index version, missing/filtered reason.
- `ActionPlan`: objective, allowed action, target scope, reason, max_action_rounds, budget remaining.
- `ActionRoundTrace`: action_plan, choice_reason, observation, verification_result, corrective_action, budget_consumption, final_stop_reason.
- `EvidenceQuality`: scope match, locator present, freshness/version, claim coverage, conflict state.
- `RagFallback`: evidence_missing, scope_mismatch, dynamic_fact_required, budget_exhausted, retrieval_failed, unauthorized_source.

## 5. Acceptance

| ID | Acceptance | PASS condition |
|---|---|---|
| S5-A01 | Document provenance | Every indexed chunk links to an authorized source, version and locator. |
| S5-A02 | Metadata filtering | Retrieval is strictly limited to one Store/Product/optional Variant; no cross-product result is accepted in Slice 5. |
| S5-A03 | Static/dynamic split | Price, inventory and availability are not answered from documents. |
| S5-A04 | Baseline retrieval | Known FAQ/manual/package-list questions retrieve supporting Evidence in the configured top-k. |
| S5-A05 | Bounded correction | At most `2` action rounds run total: baseline retrieval plus at most one targeted retrieval or clarification round. |
| S5-A06 | No identity mutation | ActionPlan cannot change Product/Variant identity or user constraints. |
| S5-A07 | Claim coverage | Every factual claim in the answer has matching Evidence and locator. |
| S5-A08 | Conflict handling | Conflicting or stale document versions produce fallback or explicit uncertainty. |
| S5-A09 | Missing evidence | Insufficient evidence never falls back to model common knowledge. |
| S5-A10 | Trace and replay | Query, filters, evidence, ActionRoundTrace, budgets, actions and final gate are replayable. |
| S5-A11 | Security | No secrets, raw headers, credentials or unauthorized documents enter output or trace. |
| S5-A12 | No scope expansion | No multi-product retrieval/recommendation, commerce refresh execution, Derived Evidence execution, HARD recheck execution, open network, fine-tuning, write operation or external-service CI requirement. |

## 6. Verification Matrix

| Matrix | Scenario | Expected |
|---:|---|---|
| 1 | Product FAQ with exact target | Scoped Evidence supports answer. |
| 2 | Package list question | Locator points to package-list source. |
| 3 | Manual operation step | Ordered source locator is preserved. |
| 4 | Policy applicability | Policy source remains store/product scoped. |
| 5 | Price/inventory asked through RAG path | Dynamic fact fallback/handoff, no document answer. |
| 6 | Wrong product document injected | Evidence Gate rejects scope mismatch. |
| 7 | First retrieval misses, targeted second retrieval hits | One corrective round, answer allowed. |
| 8 | Two total rounds exhausted | Budget fallback with `ACTION_ROUND_LIMIT`, no unsupported claim. |
| 9 | Conflicting document versions | Conflict fallback or explicit uncertainty. |
| 10 | Unauthorized source in manifest | Ingestion/retrieval rejects it. |
| 11 | Derived evidence recompute requested inside S5 | Handoff/deferred fallback; S5 does not execute Derived Evidence. |
| 12 | Secret-like payload in source metadata | Sanitized from trace and output. |

## 7. Open Decisions

- `OD-S05-01`: Chunking baseline and table handling.
- `OD-S05-02`: Whether Query Rewrite is needed, and only as an auxiliary retrieval query.
- `OD-S05-03`: Retriever engine selection, including whether Milvus is justified.
- `OD-S05-04`: Reranker value after baseline retrieval metrics exist.
- `OD-S05-05`: Minimum product document pack and authorization manifest shape.

## 8. Human Escalation

Stop if implementation requires public Contract changes, external hosted retrieval infrastructure, real credentials, open network, model-generated source rewriting, more than `2` total action rounds, cross-product retrieval, commerce refresh execution, Derived Evidence execution, HARD recheck execution, or any weakening of Evidence Gate / Shopify read-only boundaries.

## 9. Completion Evidence

Slice 5 may close only after all S5 acceptance rows pass, targeted and completion tests pass, document provenance and scope gates pass, dynamic fact split is proven, zero Shopify writes are preserved, and any real-source smoke is explicitly marked as authorized/non-authorized rather than silently assumed.
