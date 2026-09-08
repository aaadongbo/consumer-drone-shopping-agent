# Slice 11 Plan - Closed-beta Deployment and Release

> Status: S11-T09 PLANNING RECONCILIATION / NON-EXECUTABLE / HUMAN REVIEW REQUIRED
>
> T01-T08 and their closed-beta evidence remain immutable historical delivery
> records. This reconciliation adds only the proposed HIGH-risk T09 boundary for a
> US-market English pre-sales storefront experience. It does not authorize T09
> implementation, Workflow changes, external source acquisition, external services,
> production traffic, credential use, Shopify calls, deployment, push, merge, or
> public Contract/Architecture changes.

## 1. Goal

Promote the three-product local pilot into a controlled closed beta that can run in a
staging-like environment and be embedded in the approved Shopify storefront for a
small, explicitly authorized audience.

The Slice proves release readiness, operational guardrails, and one real three-product
acceptance run. It does not claim production scale, multi-tenant readiness, durable
high availability, complete recommendation-platform coverage, or open public traffic.

Slice 11 is the only planned deployment/release Slice before the initial closed beta.
No Slice 12 is created by this plan. Post-beta improvements remain unnumbered
operational iterations until Human review decides otherwise.

After the original closed-beta completion, read-only acceptance reconciliation found
that the delivered runtime does not yet satisfy the narrower product claim "US-market
Shopify pre-sales guide V1": the deployed corpus is `zh-CN` / China-mainland scoped,
the deterministic application path does not cover the required English recommendation
and comparison journeys, and the repository Widget is a Python presentation boundary
rather than a browser-embeddable storefront client with verified product links. T09
addresses only those gaps and does not invalidate the earlier three-product read-only
commerce acceptance.

## 2. Closed-beta Boundary

### In Scope

- Production-like composition/startup for the existing single-store, three-product
  pilot path.
- Explicit runtime configuration, environment variable validation, secret injection
  boundaries, and missing-config fail-closed startup.
- Health and readiness checks for process liveness, required configuration, adapter
  readiness, and bounded dependency smoke checks.
- CORS allowlist for the approved Widget origin(s).
- Basic in-process rate limiting and concurrency caps suitable for a closed beta.
- Safe error handling, redacted logs, trace correlation, minimum operational counters,
  and no-secret/no-payload leakage checks.
- Minimum real model or restricted intent-routing adapter only if deterministic
  routing is insufficient for the approved beta journeys.
- Embeddable Storefront Widget consuming existing public response semantics, with
  target display, fallback, constraints, evidence, and reset/retry interactions.
- Staging deployment path, required CI checks, rollback procedure, and one
  three-product acceptance run against approved read-only data.

### Out of Scope

- MongoDB, Redis, queues, caches, durable distributed locks, or new authoritative
  state services.
- Milvus, hosted vector databases, production indexes, rerankers, embeddings rollout,
  fine-tuning, or training-data generation.
- Complex Agent framework, open-ended ReAct, multi-agent runtime, or unrestricted
  tool use.
- Full recommendation platform, multi-store/multi-tenant support, more products,
  more languages, public launch, or production SLO claim.
- Cart, checkout, order, customer, inventory, product, collection, theme, or any other
  Shopify write operation.
- Shopify write-capable credentials, webhooks, background sync, or admin mutation
  surfaces.
- Full observability platform, SIEM, APM suite, data warehouse, Kubernetes,
  multi-region high availability, blue/green platform automation, or full incident
  management program.
- Public Contract, Product Behavior, Architecture, Accepted Decision, or dependency
  changes unless Human escalation explicitly approves the exact change.
- Creating Slice 12.

## 3. Approved Planning Baselines

Human has approved these S11 planning baselines for review. They constrain later
implementation but do not authorize the implementation Tasks themselves:

- Hosting: single-container hosting platform with separate staging and beta
  environments; the exact vendor remains open.
- Secrets: hosted platform Secret Store for deployed environments, macOS Keychain for
  local development only; `.env` files, tokens, and secret values are forbidden in
  Git.
- Model/intent: deterministic interpreter fallback plus a replaceable adapter;
  provider and model ID remain open. Model failure must fall back safely and models
  must not generate unverified facts.
- Widget origin: explicit staging/beta allowlists only; wildcard origins are
  forbidden, and the Widget may call only the Conversation API.
- CI: GitHub Actions with required lock, Ruff, unit, contract, integration, and build
  checks.
- Staging: real read-only Shopify three-product smoke, redacted logs, and Shopify
  write count equal to `0`.
- Rollback: immutable commit/image, previous known-good version retained, health
  failure stops release, one-command rollback, and no database migration.
- Post-beta roadmap: no Slice 12 is created by this plan.

## 4. Release Preconditions

Implementation must stop before deployment or external calls unless all applicable
preconditions are satisfied:

- Slice 10 completion evidence is available and labels the result
  `PILOT_READY_FOR_HUMAN_EVALUATION` rather than production-ready.
- The hosting vendor, staging/beta environment URLs, exact Secret Store, model
  provider/model ID, Widget origin values, and rollback operator are resolved before
  the Tasks that depend on them.
- Shopify credentials are demonstrably read-only and scoped to the approved store.
- Required config names and defaults are documented without committing secret values.
- DEC-012 is `ACCEPTED` in `docs/DECISIONS.md`; implementation must not change its
  semantics or public Contract boundary without separate Human approval.
- External source and corpus authorization remain valid.
- No raw Shopify response, token, secret, `.env` file, official full text, chunk
  output, index, embedding, or training data is added to Git or planning artifacts.

## 5. Minimal Runtime Contracts

Public request/response contracts should remain unchanged unless Human review accepts
a versioned Contract proposal. Slice-local deployment contracts may be internal:

- `ReleaseConfig`: typed startup configuration with explicit required keys, defaults,
  hard limits, redaction policy, and open-decision markers.
- `RuntimeReadinessReport`: metadata-only readiness verdict covering config,
  read-only adapters, CORS, rate limits, model/intent adapter, Widget origin,
  staging environment, and data/secret boundaries.
- `HealthStatus`: safe liveness/readiness result with no secret values, request
  payloads, raw Shopify payloads, or official source text.
- `OperationLedger`: read/write call counters proving Shopify write count remains
  zero.
- `WidgetEmbedConfig`: approved origin, backend endpoint, store/product page context
  mapping, and display options; no embedded credentials.

## 6. Acceptance Criteria

| ID | Acceptance | PASS condition |
|---|---|---|
| S11-A01 | Startup | Approved deployment command starts the API and Widget assets in explicit closed-beta mode with no fixture fallback unless configured for local test only. |
| S11-A02 | Config fail-closed | Missing required env, invalid origin, missing secret reference, unresolved model/intent setting, or pilot readiness failure prevents startup or turn execution with a safe diagnostic. |
| S11-A03 | Health/readiness | Liveness and readiness checks return PASS/FAIL metadata only, complete inside the health timeout, and do not make Shopify writes. |
| S11-A04 | CORS | Only explicit staging/beta Widget origin(s) can call beta endpoints; wildcard origins and unapproved origins are rejected in tests and staging smoke. |
| S11-A05 | Rate/concurrency limits | Per-session, per-store, and global provisional limits are enforced with stable retry/fallback semantics. |
| S11-A06 | Error/log safety | User errors, dependency failures, stack traces, tokens, headers, secrets, raw Shopify payloads, and official source text do not appear in public responses, logs, trace, or committed artifacts. |
| S11-A07 | Shopify write zero | Operation ledger and tests prove all Shopify operations are allowlisted reads and write-call count is `0`. |
| S11-A08 | Three-product read smoke | One authorized staging smoke run answers the approved three-product static/dynamic beta matrix using real read-only Shopify data, redacted logs, write count `0`, and current public schema. |
| S11-A09 | Model/intent fallback | The chosen model or restricted intent adapter obeys budgets; timeout, provider failure, unsupported intent, or low confidence falls back without invented facts. |
| S11-A10 | Widget interaction | Embedded Widget supports send, progressive/final answer rendering, target display, evidence/freshness display, fallback action, reset/retry, and loading/error states for the approved journeys. |
| S11-A11 | Staging smoke | Independent staging deployment passes startup, readiness, CORS, Widget, no-write, data-boundary, and one scoped journey smoke before any closed-beta traffic. |
| S11-A12 | Rollback | Rollback uses an immutable commit/image, retains the previous known-good version, stops release on health failure, runs through one command, and requires no database migration. |
| S11-A13 | CI gate | GitHub Actions required checks block release when lock, Ruff, unit, contract, integration, build, data-boundary, config validation, or Widget checks fail. |
| S11-A14 | Audit/data boundary | Completion evidence records commands actually run, source versions, config keys, operation counts, redaction checks, and known limitations without storing secrets or raw protected data. |
| S11-A15 | Closed-beta claim only | Completion reports `CLOSED_BETA_READY_FOR_HUMAN_RELEASE_DECISION`; it does not authorize public launch, production scale, durable state migration, or Slice 12. |

## 7. Provisional Release Budget

These values are provisional hard limits for the first closed beta. They are open
decisions until confirmed against the selected host, model provider, and expected beta
traffic.

| Key | Provisional default / hard limit | Stop reason |
|---|---:|---|
| `release_mode` | `closed_beta` | `INVALID_RELEASE_MODE` |
| `hosting_runtime` | single container | `UNSUPPORTED_HOSTING_RUNTIME` |
| `pilot_product_count` | `3` | `PILOT_SCOPE_LIMIT` |
| `request_timeout_ms` | `12000` | `REQUEST_TIMEOUT` |
| `health_timeout_ms` | `1500` | `HEALTH_TIMEOUT` |
| `shopify_request_timeout_ms` | `5000` | `SHOPIFY_TIMEOUT` |
| `max_shopify_read_calls_per_turn` | `2` | `SHOPIFY_READ_CALL_LIMIT` |
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls_per_turn` | `2` | `TOOL_CALL_LIMIT` |
| `max_model_tokens_per_turn` | `1200` | `MODEL_TOKEN_BUDGET` |
| `max_response_tokens` | `900` | `RESPONSE_TOKEN_BUDGET` |
| `max_concurrent_turns_global` | `4` provisional | `GLOBAL_CONCURRENCY_LIMIT` |
| `max_concurrent_turns_per_session` | `1` | `SESSION_CONCURRENCY_LIMIT` |
| `rate_limit_per_session_per_minute` | `6` provisional | `SESSION_RATE_LIMIT` |
| `rate_limit_per_store_per_minute` | `30` provisional | `STORE_RATE_LIMIT` |
| `allowed_widget_origins` | explicit allowlist only | `ORIGIN_NOT_ALLOWED` |
| wildcard CORS origins | forbidden | `WILDCARD_ORIGIN_FORBIDDEN` |
| Shopify write calls | `0` | `SHOPIFY_WRITE_FORBIDDEN` |
| `log_redaction_required` | `true` | `REDACTION_REQUIRED` |
| `log_retention_days` | `7` provisional metadata-only | `LOG_RETENTION_LIMIT` |
| `deployment_rollback_window_minutes` | `30` provisional | `ROLLBACK_WINDOW_EXCEEDED` |

## 8. Verification Cadence

- Each Task runs targeted checks for the files and behavior it changes.
- External-service, security, release, public Contract, dependency, or production
  traffic boundaries stop for Human decision before implementation proceeds.
- A pre-T02 Data Readiness artifact may prepare a candidate seed/synthetic query set
  in external Data-Staging only, with hashed Git-safe metadata and checksum sidecars.
  This does not create a Golden Set, training data, implementation authority, or
  permission to start `S11-T02`.
- Full suite, real three-product acceptance, data/secret scan, staging smoke, rollback
  evidence, and final independent Slice review occur only at Slice completion.
- No Task requires every earlier Task to rerun the full suite unless its own change
  invalidates the targeted evidence.
- Completion evidence records only commands actually run with real exit codes and
  results.

## 9. Human Escalation Conditions

Stop before implementation continues if S11 requires:

- Product Behavior, Architecture, public Contract, Accepted Decision, Acceptance, or
  major cross-Slice dependency changes.
- New runtime dependency, hosting service, CI provider, secret manager, observability
  platform, database, cache, queue, or external service not already approved for the
  exact Task.
- Changing the approved baseline away from single-container staging/beta hosting,
  hosted Secret Store, local macOS Keychain-only secrets, GitHub Actions required
  checks, explicit Widget origin allowlists, immutable rollback, or no database
  migration.
- Real model provider/model ID selection, credential provisioning, paid service
  activation, or provider-specific data-retention commitment.
- Any Shopify write, write-capable credential, webhook, cart/order/customer flow, or
  theme/store mutation.
- Public traffic, production launch, beta audience expansion, rollback policy change,
  security boundary relaxation, or storing beta user data beyond the approved trace
  metadata.
- Copying tokens, credentials, raw Shopify responses, official full text, chunks,
  indexes, embeddings, Golden Set labels, `.env` files, or training data into Git.
- Creating Slice 12 or broadening S11 into a general platform build.

## 10. Open Decisions

- `OD-S11-01` - Exact single-container hosting vendor for API and Widget assets.
- `OD-S11-02` - Exact hosted platform Secret Store and local Keychain integration
  mechanism.
- `OD-S11-03` - Real model provider and model ID; deterministic interpreter fallback
  and replaceable adapter baseline are accepted.
- `OD-S11-04` - Rate-limit backend; S11 default is in-process only unless approved.
- `OD-S11-05` - Exact staging/beta Widget origin values and embed mechanism.
- `OD-S11-06` - Exact GitHub Actions required check names.
- `OD-S11-07` - Staging environment URL, access control, and smoke-test authority.
- `OD-S11-08` - Rollback target, operator, previous-version retention details, and
  acceptable rollback window.
- `OD-S11-09` - Metadata log retention and beta data handling policy.
- `OD-S11-10` - Exact immutable commit/image tagging strategy for release candidates.

## 11. Completion Boundary

The original closed-beta completion through T08 remains historical evidence. The
expanded US-market V1 claim is complete only when T09 is `DONE`, the English/US
acceptance matrix has actual application-path and storefront-browser evidence,
Shopify write count remains zero, staging and rollback evidence pass, and a fresh
independent Slice review reports no blocking findings. The later Workflow Policy
session must explicitly make T09 the completion Task before implementation can begin.

The T09 completion label is `US_SHOPIFY_PRESALES_V1_ACCEPTANCE_READY`. Human release
approval, public launch, main integration, merge, push, and any post-beta roadmap
remain separate authorities. Until T09 passes, the earlier label
`CLOSED_BETA_READY_FOR_HUMAN_RELEASE_DECISION` must not be broadened into a US-English
V1 claim.

## 12. S11-T09 Planning Reconciliation — US-market English Storefront Closure

### Risk and authority

T09 is `HIGH` because it changes customer-visible Product Behavior, wires additional
application journeys into the deployed composition, introduces a real browser Widget
surface, depends on market-specific evidence, and requires a later external staging
acceptance. This planning reconciliation is non-executable. A separate reviewed and
integrated Workflow Policy must define the exact allowlist and verification profile;
T09 then requires a new current-context Human implementation authorization.

### Fixed product boundary

- Market, currency, and storefront language: United States, USD, `en-US`.
- Store: `shopify-store:bys-user-store-578412-7a11gk0u`; storefront origin remains
  `https://bys-user-store-578412-7a11gk0u.myshopify.com`.
- Products and canonical Variants remain the already approved Mini 3, Air 3, and
  Mavic 3 identities. T09 may not replace an identity or invent a Variant.
- Supported journeys are pre-sales clarification, specifications, capabilities,
  comparison, recommendation, and current read-only price/inventory/availability.
- Order, shipment, refund, return, warranty/repair, account, payment, invoice,
  address, cart, and checkout requests remain typed safe handoffs to the configured
  Shopify-native/store-support destination. They must not invoke an order, customer,
  cart, checkout, or write API.
- Shopify scopes remain exactly `read_products` and `read_inventory`; writes remain
  `0`.

### Implementation scope proposed for later authorization

1. Extend the existing deterministic/restricted application path to classify and
   answer the approved English pre-sales journeys using verified Evidence. Reuse the
   existing recommendation, comparison, Product RAG, target-resolution, and commerce
   boundaries; do not add an external model Provider.
2. Localize answer, clarification, fallback, transport-error, and handoff copy for
   `en-US` without adding a public enum or changing the public wire schema. Unsupported
   and evidence-deficient requests remain fail-closed.
3. Add a browser-embeddable Widget client that calls only the existing Conversation
   API, derives exact Product/Variant page context, resets stale context on navigation,
   renders Evidence/freshness and safe errors, and remains usable at desktop and mobile
   widths.
4. Resolve recommendation links through an internal, checksum-bound mapping from the
   approved Product/Variant identities to exact configured Shopify storefront URLs.
   Handles and support destinations must be obtained from approved store metadata;
   they may not be guessed, derived from display names, or added to the public
   Contract.
5. Admit only approved US-applicable English sources into a new append-only external
   corpus manifest. China-mainland material may be reused only when its applicability
   to the corresponding US product fact is explicitly verified. It may not support
   US warranty, regulation, pricing, packaging, or sales commitments by translation
   alone.
6. Exercise the existing 30-row Expert/Synthetic candidate set through the actual
   application path. Human review is required before any row is frozen or described
   as approved; fixture-label validation alone is not runtime acceptance.
7. After local verification, run one separately authorized staging/browser acceptance
   with a new explicit HTTP, Conversation-turn, and Shopify-read budget. No exhausted
   smoke budget may be reused or silently reset.

### Acceptance additions

| ID | Acceptance | PASS condition |
|---|---|---|
| S11-A16 | English pre-sales journeys | `en-US` clarification, specification, comparison, recommendation, and commerce questions traverse the actual application path and return English verified answers or explicit safe fallbacks. |
| S11-A17 | Target continuity | Current Product/Variant, pronoun follow-up, product switch, and Variant switch preserve the intended scope; stale page context is never reused after navigation. |
| S11-A18 | Recommendation grounding | Every recommendation/comparison claim is bound to admitted Evidence; insufficient evidence produces clarification or fallback rather than a forced recommendation. |
| S11-A19 | US-market evidence | USD price is read from the approved US Shopify store, and US-sensitive specifications, packaging, availability, warranty, regulatory, and sales claims use explicitly US-applicable sources or report an evidence gap. |
| S11-A20 | Browser Widget | The real Shopify page can load the Widget, send a turn, render answer/evidence/fallback/error states, reset safely, and remain usable at approved desktop and mobile viewports. |
| S11-A21 | Storefront links | Product links are clickable and resolve to the exact approved Shopify Product/Variant destination; no handle, support URL, or destination is guessed. |
| S11-A22 | Pre-sales handoff | Order, logistics, refund, return, warranty/repair, account, payment, invoice, address, cart, and checkout requests use existing typed handoff semantics, call no excluded Shopify surface, and link only to an explicitly configured support destination. |
| S11-A23 | Failure and operations | Shopify 401/429/timeout, corpus failure, budget exhaustion, and unsupported intent remain distinguishable, redacted, non-fabricating, observable, and recoverable through the existing token and rollback runbooks. |

### Explicit non-goals

- Hybrid runtime, BGE-M3 serving, reranking, vector databases, Redis, MongoDB, or a
  new model Provider. The offline Hybrid verdict remains `NOT_ADOPTED`.
- Customer-service, order, shipment, payment, account, cart, checkout, refund, return,
  warranty, repair, or Shopify write implementation.
- New public Contract fields or enums, Architecture changes, dependency changes,
  Shopify scope/data changes, public launch, or Slice 12.
- Treating synthetic fixtures, translated China-mainland material, or a temporary
  access-token smoke as evidence of real-user satisfaction or long-term operations.

### Decisions required before T09 implementation or staging

- Exact internal files and tests permitted by the T09 Workflow Policy.
- Exact approved Shopify storefront Product/Variant URLs and configured support URL.
- Exact official US-English source list, immutable source checksums, applicability
  annotations, and Data-Staging manifest identity.
- Whether the browser Widget is injected through a theme app extension, an approved
  theme snippet, or another explicitly selected non-write delivery mechanism.
- A fresh staging acceptance budget and authority for browser/storefront access,
  Render deployment, and read-only Shopify calls.
- Exact deployed commit/deployment ID to use as the acceptance and rollback boundary.
