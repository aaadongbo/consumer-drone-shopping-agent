# Slice 6 Ordered Implementation Tasks — Evidence-based Recommendation

> 状态：APPROVED PLANNING BASELINE / Implementation not yet authorized
>
> Slice 6 的目标、Scope、Acceptance、预算与 Task 表已经过 Human Planning Review。下表现在使用正式 Task 状态；S06 workflow policy 已预配置并随本 baseline 激活。`NOT_STARTED` 不构成 Implementation authority：开始 S06-T01 前仍须取得单独的 Slice Implementation 授权。

Slice 6 承接 Slice 5 未执行的 multi-product evidence collection、commerce refresh、HARD recheck 和 Derived Evidence。它仍使用 `max_action_rounds = 2 total`：第 1 轮包含初始候选证据读取；最多第 2 轮执行一个 allowlisted corrective action。

Provisional budget config:

| Key | Provisional hard limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Candidate evidence bundle contract | NOT_STARTED | Slice 5 completion + Slice 6 planning baseline |
| T02 | Per-product RAG evidence collection plan | NOT_STARTED | T01 |
| T03 | Commerce refresh and HARD recheck plan | NOT_STARTED | T01 |
| T04 | Derived Evidence computation | NOT_STARTED | T02, T03 |
| T05 | Recommendation explanation and degradation | NOT_STARTED | T04 |
| T06 | Multi-product recommendation walking skeleton | NOT_STARTED | T05 |
| T07 | Slice 6 verification matrix and completion evidence | NOT_STARTED | T06 |

## T01 — Candidate evidence bundle contract

- **Goal**：定义每个候选的 Catalog/Shopify/RAG/Derived Evidence bundle。
- **Why**：多商品推荐只有在每个候选的证据包隔离后，才能避免跨商品理由污染。
- **Scope**：未来 `backend/evidence/` bundle value objects；unit/contract tests；tasks execution record。
- **Contract**：`CandidateEvidenceBundle`、candidate identity、catalog evidence、commerce evidence、rag evidence、derived evidence、coverage state。
- **Acceptance**：bundle 与 candidate identity 一致；公共 schema 变化先停 Human checkpoint；不同候选 Evidence 不共享 mutable state。
- **Verification**：Contract + Unit.
- **Dependencies**：Slice 5 completion + Slice 6 planning approval.
- **Out of Scope**：真实推荐文案、RAG retrieval execution、commerce refresh execution。

## T02 — Per-product RAG evidence collection plan

- **Goal**：为每个 Product/Variant 分配独立 evidence objectives 与检索预算。
- **Why**：推荐最多三款 Product，必须避免单个文档丰富的商品占满证据预算。
- **Scope**：未来 `backend/agent/` evidence plan；`backend/evidence/` coverage state；integration with Slice 5 retriever。
- **Contract**：`RecommendationActionPlan` 的 candidate set、evidence objectives、per-product budgets、ActionRoundTrace。
- **Acceptance**：每个候选只接收自身 scoped Evidence；缺证有 coverage state；预算耗尽用 exact stop reason 记录。
- **Verification**：Unit + Integration with Slice 5 retriever.
- **Dependencies**：T01.
- **Out of Scope**：multi-product retrieval 算法定案、reranker 固化、开放网络。

## T03 — Commerce refresh and HARD recheck plan

- **Goal**：推荐解释前刷新动态事实并复核 HARD eligibility。
- **Why**：推荐合法性依赖当前价格、库存和可售状态，不能沿用旧 commerce facts。
- **Scope**：未来 `backend/agent/` refresh plan；`backend/catalog/` HARD recheck adapter；`backend/evidence/` commerce Evidence；zero-write tests。
- **Contract**：`RecommendationActionPlan` commerce refresh needs、Shopify ToolResult、CandidateEvidenceBundle commerce evidence。
- **Acceptance**：动态事实失败、过期或 identity mismatch 时 fail closed；不使用 stale facts；Shopify write count 为 0。
- **Verification**：Integration + zero-write ledger.
- **Dependencies**：T01.
- **Out of Scope**：Shopify write、真实 credentials、retry/backoff framework、状态持久化重构。

## T04 — Derived Evidence computation

- **Goal**：计算预算余量、差价、重量/续航/电池差等可复算 Evidence。
- **Why**：推荐解释经常需要“更便宜多少”“轻多少”等派生事实，必须由已验证输入计算。
- **Scope**：未来 `backend/evidence/` deterministic derivation utilities；unit tests with table fixtures。
- **Contract**：`DerivedEvidence` formula/rule、input evidence IDs、computed value、unit、observed/catalog version。
- **Acceptance**：每项派生值绑定输入 Evidence、单位和公式；输入缺失则不生成；不做模型自由数学。
- **Verification**：Unit + property-like table.
- **Dependencies**：T02, T03.
- **Out of Scope**：不可解释评分、学习排序、Product RAG retrieval。

## T05 — Recommendation explanation and degradation

- **Goal**：生成理由、取舍、coverage disclosure 和 fallback/degradation。
- **Why**：证据不足不能阻塞所有价值，但正式推荐理由必须只表达被证据支持的内容。
- **Scope**：未来 `backend/agent/` explanation policy；`backend/evidence/` coverage checks；contract/integration tests。
- **Contract**：`RecommendationExplanation`、supported reasons、tradeoffs、binding map、`RecommendationFallback`。
- **Acceptance**：每条理由都有 Evidence 或被删除/降级；UNKNOWN 明确披露；关键 coverage 不足时 fallback。
- **Verification**：Contract + Integration.
- **Dependencies**：T04.
- **Out of Scope**：正式 UI、个性化学习排序、利润/库存去化排序。

## T06 — Multi-product recommendation walking skeleton

- **Goal**：打通 constraints -> eligibility -> per-product evidence -> derived -> explanation -> response。
- **Why**：Slice 6 需要证明推荐输出在多候选、多证据、多降级路径下仍可回放。
- **Scope**：未来 `backend/application/` recommendation flow；`backend/agent/` plan; `backend/catalog/` eligibility; `backend/evidence/` bundle; tests。
- **Contract**：CandidateEvidenceBundle、RecommendationActionPlan、DerivedEvidence、RecommendationExplanation、existing AnswerEnvelope or versioned proposal。
- **Acceptance**：最多三款 Product；每款 Variant 明确；no-match 与 partial-evidence fallback 可靠；所有 facts 绑定对应候选。
- **Verification**：Integration + E2E.
- **Dependencies**：T05.
- **Out of Scope**：Slice 7 storefront、真实外部服务、push、完整比较引擎。

## T07 — Slice 6 verification matrix and completion evidence

- **Goal**：覆盖 S6-A01～S6-A12 和 Matrix #1～#12。
- **Why**：Slice 6 完成前需要证明推荐合法性、动态事实、派生证据、降级和零写边界都可靠。
- **Scope**：tests、eval fixtures、tasks execution evidence、Slice completion review。
- **Contract**：S6 verification matrix、ActionRoundTrace、RecommendationFallback、zero-write evidence。
- **Acceptance**：full suite、scope、evidence、dynamic fact、derived replay、zero-write gates 通过。
- **Verification**：Static + Unit + Contract + Integration + E2E + full suite.
- **Dependencies**：T06.
- **Out of Scope**：Slice 7 implementation、fine-tuning、feature delivery workflow changes。

## Human Escalation

公共 Contract、Product Behavior、Architecture、重大依赖、外部服务、open-network Evidence、Shopify write、learning ranking 固化、Evidence Gate 放宽或超过 `2` 个 total action rounds 都必须升级。
