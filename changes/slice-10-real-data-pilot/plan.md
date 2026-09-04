# Slice 10 Plan - Real-data Read-only Pilot

> Status: APPROVED PLANNING BASELINE / NON-EXECUTABLE
>
> Human has accepted the Slice 10 goal, scope, acceptance criteria, provisional
> budget, and ordered Task table. This approval authorizes the planning baseline
> only; it does not authorize live credentials, external network access, Shopify
> calls, implementation, workflow activation, push, or production deployment.

## 1. Goal

Connect the existing Product/Variant identity, Evidence, fallback, Shopify-read, and
controlled-retrieval boundaries to approved real data for a three-product local pilot.
The smallest target is one existing Conversation API path that can answer:

1. one current Variant commerce question from a real read-only Shopify result; and
2. one static product-document question from an approved external zh-CN corpus with a
   resolvable citation locator.

The Slice proves adapter and composition boundaries. It does not claim production
deployment, production retrieval quality, or a customer-ready Widget.

Slice 10 is the final real-data pre-release Slice. If it succeeds, Slice 11 is the
only planned deployment/release Slice; no Slice 12 is planned before the initial
closed-beta release.

## 2. Pilot Boundary

### In Scope

- One Shopify store and exactly three approved consumer-drone Products.
- Stable Shopify Product and Variant identities for every pilot commerce result.
- A protocol-independent, read-only Shopify adapter using an injected transport.
- The approved external corpus and corrected chunk manifest for the same three
  Products, read outside the repository without copying raw text or source files into
  Git.
- Existing single-target scope, static/dynamic split, Evidence, fallback, trace, and
  `AnswerEnvelope` semantics.
- An internal composition root that selects explicit `fixture` or `pilot` adapters.
- Local/test-environment API and E2E verification for a bounded pilot matrix.

### Out of Scope

- Shopify mutations, carts, orders, customers, inventory updates, or write-capable
  credentials.
- Production deployment, public traffic, a production storefront Widget, CDN, or
  browser packaging.
- New public Contract fields or version changes.
- Embeddings, vector databases, Milvus, reranking, persistent indexes, hosted
  retrieval, model fine-tuning, or training-data generation.
- Open-web/community evidence, multi-store support, additional products, languages,
  or regions.
- Copying raw PDFs, official full text, Shopify exports, generated chunks, indexes,
  embeddings, credentials, or Golden Set labels into this repository.
- Replacing deterministic target, constraint, eligibility, or Evidence gates with an
  LLM. A model provider remains deferred until the real-data pipeline is trustworthy.

## 3. Readiness Preconditions

Implementation must fail closed before external calls unless all applicable
preconditions are satisfied:

- The store identifier is explicitly configured and matches the approved pilot store.
- Each of the three Products has a stable Shopify Product ID.
- Every commerce-bearing option has a stable Variant ID owned by that store/Product;
  name-only, position-only, or unresolved Variant mappings are rejected.
- The read credential has an auditable read-only scope. Any mutation-capable surface
  requires Human escalation before use.
- The external corpus manifest, corrected chunk manifest, checksum, language, region,
  Product scope, source version, ordinal, extraction method, and locator bindings pass
  the existing S08/S09 gates.
- Data authorization and copyright/source-review records remain valid.
- Required secrets are supplied outside Git and can be redacted from errors and trace.

The current candidate Shopify snapshot is not current commerce truth while its Variant
IDs are unresolved. Missing stable Variant identity therefore produces a readiness
`HOLD`, not a default Variant selection.

### Parallel Preparation Before Coding

The readiness report must expose two independent lanes instead of one opaque verdict:

- **Shopify lane**: stable Product/Variant IDs, store ownership, demonstrably read-only
  credential, and the minimum Storefront GraphQL/Admin GraphQL choice.
- **Corpus lane**: corrected chunk manifest, source authorization, checksums, ordinals,
  extraction method, locators, and overlay policy.

T01 may complete with one lane in `HOLD` as long as the report is truthful and no
external call is made for that lane. Corpus-reader work can proceed when the corpus
lane is `GO`, even if the Shopify lane is still `HOLD`; the Shopify adapter cannot
start until the Shopify lane is `GO` and external access is explicitly authorized.

Before T01 implementation, run and record one fresh full-project baseline. After that,
T01 through T05 use only their targeted checks; the full suite runs again once at T06.

## 4. Minimal Internal Contracts

Reuse existing public contracts unchanged. Slice-local additions should remain behind
existing ports:

- `PilotDataReadinessReport`: store scope, approved Product/Variant mappings, corpus
  versions, credential-scope verdict, accepted/rejected prerequisites, and exact stop
  reason. It contains no secret or source text.
- `ShopifyReadTransport`: injected typed query boundary; it exposes no mutation or
  generic operation dispatcher.
- Existing `ShopifyReadPort`: continue to expose only `get_products`, `get_variants`,
  and `refresh_commerce_state` semantics.
- `ExternalCorpusReader`: loads only approved source regions into an ephemeral process
  boundary after manifest and scope validation.
- `PilotComposition`: explicitly selects `fixture` or `pilot` mode and wires existing
  application services to approved adapters.

If the current `AnswerEnvelope`, Evidence, ToolResult, Product/Variant identity, or
Conversation API cannot express the pilot without semantic change, stop for Human
reconciliation rather than expanding the public wire schema in this Slice.

## 5. Acceptance Criteria

| ID | Acceptance | PASS condition |
|---|---|---|
| S10-A01 | Stable identity | Every real commerce fact is bound to an approved store/product/variant mapping; unresolved or foreign Variant IDs stop before a fact is produced. |
| S10-A02 | Read-only Shopify | The adapter has no mutation surface, all observed operations are allowlisted reads, and write-call count is zero. |
| S10-A03 | Current dynamic truth | Price, inventory, and availability come only from the current Shopify read result and preserve `observed_at`; staged snapshots and documents cannot supply them. |
| S10-A04 | Approved static evidence | A static pilot answer uses only the approved external corpus version and includes a resolvable source/page/chunk locator. |
| S10-A05 | Scope isolation | Store/Product/Variant and corpus scope are checked before scoring or composition; cross-product and Mavic 3/Cine overlay injections fail closed. |
| S10-A06 | Static/dynamic separation | Dynamic questions route to Shopify; static document questions route to controlled retrieval; neither source impersonates the other. |
| S10-A07 | Explicit runtime mode | Fixture mode cannot silently become pilot mode, and pilot mode cannot silently fall back to fixture facts. |
| S10-A08 | Actionable failure | Missing credential, timeout, authorization failure, unresolved identity, invalid corpus, no scoped evidence, and budget exhaustion return an exact safe fallback without stale facts. |
| S10-A09 | Existing wire compatibility | Pilot ANSWER/FALLBACK responses round-trip through the current public schema with no public Contract change. |
| S10-A10 | Data and secret boundary | No raw source/export/index/training artifact or credential enters Git, response text, logs, or trace. |
| S10-A11 | Bounded execution | The configured call, retrieval, candidate, token, and deadline limits are enforced with observable stop reasons. |
| S10-A12 | Pilot E2E | The approved local pilot matrix passes for all three Products, including success, identity mismatch, source failure, and zero-write cases. |
| S10-A13 | No production claim | Completion evidence is labeled local pilot only and cannot authorize production deployment, Golden Set freeze, embeddings, or training. |

## 6. Provisional Pilot Budget

| Key | Limit | Stop reason |
|---|---:|---|
| `pilot_product_count` | `3` | `PILOT_SCOPE_LIMIT` |
| `max_shopify_read_calls` | `2` per turn | `SHOPIFY_READ_CALL_LIMIT` |
| `max_shopify_attempts` | `2` total | `SHOPIFY_ATTEMPT_LIMIT` |
| `shopify_request_timeout_ms` | `5000` | `SHOPIFY_TIMEOUT` |
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_scoped_candidates` | `10` | `SCOPED_CANDIDATE_LIMIT` |
| `max_retrieval_tokens` | `4000` | `RETRIEVAL_TOKEN_BUDGET` |
| `turn_deadline_ms` | `12000` | `TURN_DEADLINE` |
| Shopify write calls | `0` | `SHOPIFY_WRITE_FORBIDDEN` |

The limits are provisional pilot gates, not production SLOs. One retry, when allowed,
must remain inside the two total Shopify attempts and the turn deadline.

## 7. Pilot Verification Matrix

| Matrix | Scenario | Expected |
|---:|---|---|
| 1 | Three Products and their Variant mappings pass the readiness gate | Exact store/product/variant identities are accepted. |
| 2 | Product has no stable Variant ID | `HOLD` / identity fallback; no commerce query and no default Variant. |
| 3 | Current price/availability question | Current Shopify read result, Variant scope, and `observed_at` are preserved. |
| 4 | Staged Shopify snapshot offered as current truth | Rejected before answer composition. |
| 5 | Static official-document question | Same-Product evidence with resolvable external locator is returned. |
| 6 | Cross-product or excluded overlay candidate is injected | Rejected before retrieval scoring or Evidence construction. |
| 7 | Dynamic question reaches the corpus path | Routed away or safely rejected; no document-derived commerce fact. |
| 8 | Shopify timeout/rate-limit/authorization failure | Existing safe fallback, no stale fact, bounded attempts. |
| 9 | Corpus/manifest/checksum is missing or mismatched | Exact corpus fallback; no common-knowledge answer. |
| 10 | Fixture and pilot modes are intentionally selected | Each mode uses only its configured adapters; no silent fallback between them. |
| 11 | Secret/raw-data/no-write scan | No sensitive or forbidden artifact and zero Shopify/Data-Staging writes. |
| 12 | Local Conversation API replay | Current public request/response schema, trace correlation, Evidence binding, and deadlines pass. |

## 8. Verification Cadence

- T01, T02, and T04: targeted tests, related lint, scope checks, and no independent
  Task review.
- T03: one focused immutable-boundary review for real Shopify transport, credential
  redaction, external-network behavior, and zero-write enforcement.
- T05: one focused review of the real three-product Pilot E2E boundary.
- T06: one full suite and one final Slice review.
- No Task repeats the full suite, creates review-only worktrees, or changes the
  Workflow engine without a demonstrated blocker and separate Human authorization.

## 9. Human Escalation Conditions

Stop before implementation continues if it requires:

- Changing Product Behavior, Architecture, public Contracts, Acceptance, or an
  Accepted Decision.
- Adding a runtime dependency, SDK, hosted service, secret manager, database, queue,
  cache, persistent index, or observability platform.
- Using a credential that is not demonstrably read-only, adding any Shopify mutation,
  or broadening the store/product scope.
- Resolving Product/Variant identity by guess, display order, fuzzy name alone, or
  cross-Product fallback.
- Copying external source text, PDFs, Shopify exports, chunks, embeddings, indexes,
  secrets, or evaluation labels into Git.
- Changing corpus authorization, licensing assumptions, region/language scope, or
  Mavic 3/Cine policy.
- Enabling public traffic, production deployment, model-generated facts, or customer
  data collection.

## 10. Open Decisions

- Shopify Storefront GraphQL versus Admin GraphQL for the minimum read-only pilot.
- Credential provisioning and rotation mechanism for local/test environments.
- Whether the external corpus reader uses the existing local Data-Staging path or a
  separately approved object-store adapter.
- Whether a new runtime HTTP dependency is necessary; implementation must first test
  the smallest replaceable transport option and escalate before adding one.
- Recorded-response strategy for deterministic integration tests without committing
  private Shopify exports or secrets.
- Whether pilot success justifies a later production retrieval/index Slice.

## 11. Completion Boundary

Slice 10 is complete only when the three-product local pilot matrix passes using
approved real source bindings and the current public API contract. Completion means
`PILOT_READY_FOR_HUMAN_EVALUATION`, not production readiness.

After this approved planning baseline is established, separately activate the minimum
S10 Workflow Policy and obtain the applicable implementation/external-access authority.
Implementation must start with the identity/data readiness gate, not with network code.

After Slice 10, Slice 11 is limited to closed-beta deployment essentials:

- production composition/startup, environment variables, and secret injection;
- health checks, CORS, rate limiting, safe error logging, and basic monitoring;
- the minimum bounded model/intent component only if deterministic routing is
  insufficient for the approved beta cases;
- an actual embeddable Shopify storefront Widget;
- CI, staging deployment, rollback, and one real three-product acceptance run.

The first closed beta may keep the documented single-instance in-memory conversation
state, with explicit restart-loss behavior. Redis, MongoDB, Milvus, fine-tuning, and a
complex observability platform remain deferred unless beta evidence proves they are
necessary. DEC-012 status must be reconciled before Slice 11 completion, not silently
changed by Slice 10 implementation.
