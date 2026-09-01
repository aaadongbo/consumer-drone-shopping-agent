# Slice 6 Planning — Multi-product Evidence-based Recommendation

> 状态：DRAFT / Non-executable roadmap planning
>
> 本文件提前规划 Slice 6 的多商品证据推荐。它不授权 Implementation、Task 状态推进、snapshot、commit、push 或真实外部服务配置。

## 1. Goal

在 Slice 2 的 deterministic eligibility/ranking 和 Slice 5 的 scoped Product RAG 基础上，为最多三款不同商品生成正式推荐。每个候选必须使用自身 Catalog、当前 Shopify commerce、Product RAG Evidence 和可复算 Derived Evidence；证据不足的理由降级或删除，无合格候选时不生成正式推荐。

## 2. Scope

In scope:

- 多候选 Evidence collection plan：每个 Product/Variant 独立证据预算、scope filter 和 coverage gate。
- HARD eligibility 与动态 Shopify refresh 的一致性复核。
- Derived Evidence：预算余量、价格差、重量差、续航差、套装电池差等可复算事实。
- 推荐理由、取舍、coverage disclosure 和 no-match / partial-evidence fallback。
- 受限 ActionPlan 在补文档与 refresh commerce 之间选择，但仍为 `max_action_rounds = 2 total` 且 allowlist only；第 1 轮包含初始候选证据读取，最多第 2 轮 corrective action。
- Trace：候选筛除、证据预算、derived recompute、claim coverage 和最终排序。
- Provisional budget config and exact stop reasons:

| Key | Provisional hard limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |

Out of scope:

- 开放自治、多 Agent、跨店推荐、多语言、个性化长期画像、学习排序固化。
- Shopify write、购物车/订单/客户、真实外部服务 CI、开放网络资料。
- 完整比较引擎、正式 Widget、fine-tuning 或利润/库存去化排序。

## 3. Product Behavior

- 正式推荐最多三款不同 Product，但每款必须披露实际 Variant。
- HARD eligibility 的结果优先于任何文档或模型理由；UNKNOWN/missing HARD 不得通过。
- 推荐理由可以使用 Product RAG，但每条理由只能绑定对应候选自己的 Evidence。
- 动态价格、库存和可售状态必须来自当前 Shopify ToolResult；文档不能冒充实时事实。
- Derived Evidence 必须记录输入 Evidence 与公式/规则，且可重放。
- 若某候选缺少支持某理由的文档 Evidence，该理由降级或删除；如果关键 coverage 不足，则整体 fallback 或暂定候选。

## 4. Minimal Contracts

Planning-level concepts only:

- `RecommendationActionPlan`: candidate set, evidence objectives, commerce refresh needs, per-product budgets, max_action_rounds.
- `ActionRoundTrace`: action_plan, choice_reason, observation, verification_result, corrective_action, budget_consumption, final_stop_reason.
- `CandidateEvidenceBundle`: candidate identity, catalog evidence, commerce evidence, rag evidence, derived evidence, coverage state.
- `DerivedEvidence`: formula/rule, input evidence IDs, computed value, unit, observed/catalog version.
- `RecommendationExplanation`: supported reasons, tradeoffs, rejected/unknown dimensions, binding map.
- `RecommendationFallback`: no_match, insufficient_evidence, commerce_refresh_failed, rag_unavailable, coverage_below_threshold.

Any public `AnswerEnvelope` or client payload extension must be proposed as a versioned Contract change and stop at Human checkpoint.

## 5. Acceptance

| ID | Acceptance | PASS condition |
|---|---|---|
| S6-A01 | Candidate legality | Only currently available variants satisfying all known HARD constraints can be formal recommendations. |
| S6-A02 | Product cap | Output contains at most three different Products and discloses actual Variant identity. |
| S6-A03 | Per-product evidence | Every candidate uses only its own Product/Variant evidence. |
| S6-A04 | Dynamic/static split | Price, inventory and availability come only from current Shopify ToolResult. |
| S6-A05 | Derived evidence | Computed margins/deltas are deterministic and bind to input Evidence. |
| S6-A06 | Reason coverage | Every recommendation reason has claim-evidence binding or is removed/degraded. |
| S6-A07 | Tradeoff clarity | Unknown, missing and not-applicable dimensions are disclosed, not hidden. |
| S6-A08 | No match | No eligible variants produce fallback, not formal recommendations. |
| S6-A09 | Partial evidence | Missing non-critical evidence yields scoped degradation; missing critical evidence fails closed. |
| S6-A10 | Bounded correction | ActionPlan runs at most `2` total rounds and stops with exact budget reason when exceeded. |
| S6-A11 | Determinism | Same input/catalog/commerce/index versions produce same candidates, ordering and reasons. |
| S6-A12 | Safety | No Shopify writes, cross-store reads, open network, secrets in trace, or unplanned external dependency. |

## 6. Verification Matrix

| Matrix | Scenario | Expected |
|---:|---|---|
| 1 | Budget + travel recommendation | Up to three legal Product groups with Variant disclosure. |
| 2 | HARD no-match | Blocking constraints shown, no formal candidates. |
| 3 | One candidate lacks RAG reason evidence | Reason removed/degraded for that candidate only. |
| 4 | Commerce refresh fails | Dynamic reason fallback, no stale price/inventory. |
| 5 | Derived budget margin | Calculation binds to current price Evidence and budget constraint. |
| 6 | Weight/flight-time tradeoff | Derived or catalog facts bind to correct candidate. |
| 7 | Cross-product evidence injection | Evidence Gate rejects mismatched candidate. |
| 8 | UNKNOWN HARD field | Variant excluded, not treated as unsupported or zero. |
| 9 | Tie/replay | Stable ordering and identical explanation under same versions. |
| 10 | RAG unavailable | Recommendation degrades only where evidence is non-critical; otherwise fallback. |
| 11 | More than three eligible Products | Exactly three Product groups, deterministic selection. |
| 12 | Trace audit | Candidate, rejection, evidence, derived and answer records share correlation ID. |

## 7. Open Decisions

- `OD-S06-01`: Multi-product retrieval allocation: global top-k, per-product quota or two-stage.
- `OD-S06-02`: SOFT ranking weight adjustments beyond deterministic baseline.
- `OD-S06-03`: Whether generic reranker improves per-product evidence coverage enough to justify latency.
- `OD-S06-04`: Critical versus non-critical evidence thresholds for formal versus tentative recommendation.
- `OD-S06-05`: Client payload shape for multi-card recommendations.

## 8. Human Escalation

Stop for public Contract changes, learning ranking, major dependencies, external services as gates, cross-store behavior, Shopify writes, open-network evidence, more than `2` total action rounds, or any attempt to let model text override eligibility or Evidence Gate.

## 9. Completion Evidence

Slice 6 closes only when every S6 acceptance row has replayable evidence, full suite passes, recommendation reasons are bound to candidate evidence, dynamic facts are current, zero writes hold, and all open decisions touched by implementation have recorded outcomes or are explicitly deferred.
