# Slice 4 Planning — Variant 比较

> 状态：DRAFT / Non-executable roadmap planning
>
> 本文件只定义 Slice 4 的最小实现边界。它不授权 `S04-T01`、Task 状态推进、snapshot、commit、integration、push、依赖安装或业务代码修改。进入实现前仍需 Human Review、planning baseline、workflow policy activation 与单独的 Slice implementation authority。

### Data identity prerequisite

当前 Shopify staging snapshot 包含 3 个 Product，每个只有一条 Default Title 记录，但 `variant_id` 为 `null`（`NOT_IN_STANDARD_SHOPIFY_PRODUCT_EXPORT`）。这不是可执行的 Variant identity。进入 Slice 4 实现前，必须先获得经过授权且可追溯的稳定 Variant ID 映射；不得用 Product ID、SKU 或自造值替代。未完成映射时，规划可审查但实现必须保持不可执行。

## 1. Goal

在同一 Store 内，安全比较 `2` 至 `4` 个已明确的 Variant，并以每个成员自己的 Product / Variant identity、规范化事实、动态事实新鲜度与 Evidence 输出可追溯的差异。比较是本轮临时工作集：不得把多个成员折叠成单对象，也不得改变已有 confirmed single-object Conversation Context。

首个最小闭环只接受同一 Product 下的 `2` 至 `4` 个 Variant；每个 member 仍须分别保留该 Product identity。跨 Product 比较不在本 Slice 默认实现，先返回明确的 typed deferral / fallback，等待 Open Decision 决定是否由后续 Slice 承接。

## 2. Scope and boundaries

In scope:

- 从 Slice 3 的 `COMPARISON_SET` typed handoff 校验和物化一个 bounded `ComparisonSet`。
- 显式 member 与当前上下文来源的区分；同一 Product 的显式 Variant 和已确认单对象可组成集合，但不能猜测、默认首项或以页面对象补齐缺失成员。
- 每个成员的 Store / Product / Variant identity、source/provenance、resolution reason、catalog revision，以及 per-member Evidence binding。
- 面向当前约束与购买决策的最小结构化事实读取、KNOWN / UNKNOWN / NOT_APPLICABLE 的显式表达，以及比较输出与 trace。
- 仅对输出的动态 price / inventory / availability 读取当前只读 Shopify 事实；所有动态事实均附 observed time / freshness，失败或过期时降级，不借用文档或旧值。
- clarification、typed deferral、evidence-missing、dynamic-fact-unavailable 与 traceable fallback。

Out of scope:

- 跨 Product 比较的正式行为、跨 Store、超过四个成员、变体代选策略扩展、推荐 / ranking / Derived Evidence。
- Slice 5 Product RAG、文档摄取、检索、Agentic action loop 或以文档回答动态事实。
- Slice 6 multi-product recommendation、正式 Widget wire schema、生产 UI / 流式协议、开放网络、真实外部服务和任何 Shopify write。
- 修改 public `AnswerEnvelope`、现有 wire Contract、Architecture、Accepted Decision、workflow implementation、依赖或 Slice 3 行为；若确有需要，先停在 Human checkpoint。

## 3. Product behavior

- 比较请求只有在恰好 `2` 至 `4` 个可解析成员、所有成员属于同一 Store、且首版成员属于同一 Product 时才继续。一个成员缺失、歧义、foreign-store、product/variant ownership mismatch 或成员重复都请求澄清或返回 typed fallback。
- 每个 member 都必须最终是具体 Variant。仅 Product reference 不允许选择“第一个”；若未来采用约束驱动的代选，必须披露选择理由、仍保留 Product 来源，并先经 Human Decision。
- 显式 reference 优先于当前 confirmed single-object；confirmed context 只能作为一个明确成员来源，不能在没有明确比较意图时自行扩展集合。Page Context 不能补齐比较成员。
- 每个 `ComparisonFact` 和 Evidence 只能绑定其所属 member 的 identity；不得拼接不同 Variant、不得把一个成员的价格、库存、规格或来源用于另一个成员。
- 动态价格、库存、availability 只接受当前只读 Shopify `ToolResult`；输出必须带 freshness / observed time。读取失败、identity mismatch 或超出 freshness policy 时该格标为 unavailable / unknown 并给出可行动 fallback。
- 输出披露实际 Variant、per-member provenance、事实状态、证据与比较范围；关键差异没有正确 member Evidence 时不形成确定结论。
- 本 Slice 不写 ConversationState，特别是不改变 confirmed single-object context；trace 记录 handoff、member resolution、fact/evidence source、freshness、降级及 correlation id。

## 4. Minimal Slice-local contracts

以下为 planning-level internal concepts，不修改公开 wire schema：

- `ComparisonSet`: correlation_id, store_id, members (`2..4`), source intent, scope status, fallback / clarification reason。
- `ComparisonMember`: member_id, product_id, variant_id, explicit-or-context provenance, resolution reason, catalog revision, display identity。
- `MemberProvenance`: source kind (`EXPLICIT`, `CONFIRMED_CONTEXT`), original reference / context revision, resolver outcome; Page Context 不得成为隐式补全来源。
- `ComparisonFact`: member_id, field key, normalized value / unit, state (`KNOWN`, `UNKNOWN`, `NOT_APPLICABLE`, `UNAVAILABLE`), source class, observed/catalog version, freshness when dynamic。
- `ComparisonEvidenceBinding`: comparison_fact_id / claim_id, member_id, Evidence identity and locator, scope and freshness verdict。
- `ComparisonAnswer` or typed internal handoff: comparison set, rows / differences, per-member bindings, disclosure, fallback, trace reference. Public response extension remains a future versioned proposal.

## 5. Acceptance

| ID | Acceptance | PASS condition |
|---|---|---|
| S4-A01 | Bounded set | Only 2–4 distinct, resolvable members in one Store enter a comparison. |
| S4-A02 | Product / Variant identity | Every member resolves to one Variant with its owning Product; no Product/Variant mixing or default first selection. |
| S4-A03 | Source precedence | Explicit and confirmed-context provenance are displayed per member; Page Context never silently adds a member. |
| S4-A04 | Context isolation | A comparison does not mutate confirmed single-object Conversation Context. |
| S4-A05 | Scope boundary | Initial execution accepts same-Product variants only; cross-Product sets get an explicit typed deferral / fallback. |
| S4-A06 | Fact state clarity | KNOWN, UNKNOWN, NOT_APPLICABLE and dynamic-unavailable remain distinct in output and trace. |
| S4-A07 | Per-member evidence | Each key fact / difference is bound only to Evidence owned by the corresponding member. |
| S4-A08 | Dynamic freshness | Price, inventory and availability come from current read-only Shopify results with freshness disclosure; stale or failed reads do not become facts. |
| S4-A09 | Clarification and fallback | Ambiguous, incomplete, duplicate, foreign-store or ownership-invalid sets do not guess and provide a next action. |
| S4-A10 | Read-only and trace | Zero Shopify writes; identity, provenance, fact/evidence, freshness and degradation share a replayable correlation id. |
| S4-A11 | No premature expansion | No RAG, recommendation, Derived Evidence, official Widget schema, cross-Product behavior, dependency or external-service completion gate is introduced. |

## 6. Verification matrix

| Matrix | Scenario | Expected |
|---:|---|---|
| 1 | Two explicit variants of one Product | Correct two-member identity, rows and per-member provenance. |
| 2 | Explicit variant plus confirmed context variant | Both members retained; confirmed context unchanged after turn. |
| 3 | Product-only / ambiguous reference | Clarification; no first Variant selection. |
| 4 | Duplicate, one-member, five-member or foreign-store set | Bounded clarification / fallback; no comparison read. |
| 5 | Product/Variant ownership mismatch | Fail closed before facts are read. |
| 6 | Unknown and not-applicable attributes | Displayed distinctly, no unsupported inference. |
| 7 | Cross-member Evidence injection | Evidence gate rejects mismatched member binding. |
| 8 | Current dynamic reads | Price / inventory / availability carry member identity and freshness. |
| 9 | Failed or stale dynamic read | Unavailable / fallback, never a stale document substitute. |
| 10 | Cross-Product comparison request | Explicit typed deferral; no Slice 6 recommendation execution. |
| 11 | Trace audit / write ledger | Complete correlation chain and zero Shopify writes. |

## 7. Ordered implementation plan

See [tasks.md](./tasks.md). The walking skeleton progresses from set validation and identity isolation, through facts/evidence and dynamic freshness, to a single internal answer/fallback path and completion evidence. Every task remains `PLANNED` until a later Human-approved execution baseline.

## 8. Workflow policy handling

The existing policy schema could represent Slice-local scope, risk and verification configuration, but the repository's `AGENTS.md` freezes `.agents/skills/drone-slice-workflow/**` during Slice work and requires a separate governance authorization before changing it. This planning session therefore does **not** add an S04 policy entry or change workflow scripts / Skill behavior. The Tasks remain non-formal `PLANNED` roadmap rows; policy activation is a future, separately authorized governance step and never authorizes `S04-T01` by itself.

Targeted verification is required per task; completion requires the full suite, scope/diff checks, zero-write evidence and independent Slice review. All public Contract, Product Behavior, Architecture, Acceptance, Accepted Decision, external-service, Shopify-write, dependency, security/safety and workflow changes remain immediate Human escalations regardless of configured risk tier.

## 9. Open decisions

- `OD-S04-01`: Initial comparison field set and its relevance ordering from current constraints.
- `OD-S04-02`: Whether the hard `2..4` member cap remains fixed after representative UX data.
- `OD-S04-03`: Product-only member selection rule; no default selection is permitted before a Human-approved decision.
- `OD-S04-04`: Dynamic fact read scheduling: sequential deterministic reads versus bounded parallel reads, including latency and trace semantics.
- `OD-S04-05`: Per-member Evidence / locator binding shape and whether existing internal evidence types suffice.
- `OD-S04-06`: Whether cross-Product comparison is deferred to Slice 6, a later dedicated Slice, or admitted under a separately approved S4 expansion.
- `OD-S04-07`: Freshness window, partial-dynamic-read fallback, and p95 comparison latency budget.

## 10. Human escalation conditions

Stop for a public Contract or Widget schema change; any change to Product Behavior, Architecture, Acceptance or an Accepted Decision; product-only auto-selection; cross-Product or cross-Store behavior; RAG / recommendation / Derived Evidence; dynamic reads that require real credentials or external-service gating; Shopify writes; dependency changes; parallelism that weakens trace / budget guarantees; or any Evidence, freshness, identity or read-only gate weakening.

## 11. Completion evidence

Slice 4 may close only when every S4 acceptance row has replayable evidence; targeted checks and full suite actually pass; policy scope/diff and secret checks pass; all dynamic reads prove zero writes and correct freshness; independent Slice review passes; and Human accepts the completion evidence. Closing Slice 4 does not authorize Slice 5, Slice 6, integration or push.
