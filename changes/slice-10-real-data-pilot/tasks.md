# Slice 10 Tasks - Real-data Read-only Pilot

> Status: APPROVED PLANNING BASELINE / NON-EXECUTABLE
>
> Human has accepted the Slice 10 goal, scope, acceptance, provisional budgets, and
> ordered Task table. The rows remain planning records rather than formal workflow
> states until S10 Workflow Policy activation; this baseline does not authorize
> implementation, live credentials, external network access, push, or production use.

## Ordered Tasks

| Task | Title | Planned Risk | Dependencies |
|---|---|---|---|
| T01 | Pilot identity and data-readiness gate | MEDIUM | S09 locally integrated; S10 planning approval |
| T02 | Approved external corpus reader | MEDIUM | T01 corpus lane `GO` |
| T03 | Real read-only Shopify adapter | HIGH | T01 Shopify lane `GO`; explicit external-access authorization |
| T04 | Pilot composition root | MEDIUM | T02, T03 |
| T05 | Three-product local pilot E2E | HIGH | T04 |
| T06 | Slice 10 completion evidence | HIGH | T05 |

Risk labels are proposed for later Workflow Policy review. They are not execution
authority. T03 and T05 are explicit Human boundaries because they involve real
credentials/network behavior and real-source E2E respectively.

Verification cadence is intentionally light:

- T01, T02, and T04 use targeted verification without independent Task review.
- T03 and T05 each use one focused review at their real external/risk boundary.
- T06 runs the full suite once and performs the final Slice review.
- Workflow implementation is frozen unless a demonstrated blocker requires a
  separately authorized governance change.

## T01 - Pilot Identity and Data-readiness Gate

### Goal

Produce a metadata-only readiness verdict for the three pilot Products, their stable
Variant IDs, the approved store, credential scope, corpus version, and corrected
chunk-baseline bindings.

### Why

Real adapter work is unsafe and wasteful while Variant identity, corpus provenance, or
read-only authority is unresolved.

### Scope

Read-only Shopify identity metadata and external corpus/manifest metadata; no network
call is required if the prerequisites are absent.

### Contract

Internal `PilotDataReadinessReport` with separate Shopify/corpus lane verdicts, exact
accepted prerequisites, rejected prerequisites, safe metadata, and `GO`/`HOLD`
reasons.

### Acceptance

- The report independently states Shopify-lane and corpus-lane readiness.
- Exactly three approved Products and all known commerce-bearing Variant IDs are
  assessed for stability and store/Product ownership.
- Candidate or unresolved Shopify snapshots cannot become current truth.
- Corpus and chunk manifest bindings are assessed through the existing S08/S09 gates.
- Missing credential authority, identity, manifest, checksum, or authorization returns
  a lane-specific `HOLD` without external calls.
- T01 can be `DONE` with a truthful `HOLD`; it does not promote incomplete data.

### Verification

- Unit tests for complete, missing, foreign, duplicate, and unresolved identities.
- Contract tests for safe serialization and absence of secrets/raw source text.
- Read-only checks against approved external metadata when available.
- One fresh full-project baseline before T01 changes; record the exact command, exit
  code, and result. Do not repeat the full suite in T01 through T05.

### Dependencies

S09 locally integrated and Human-approved S10 planning baseline.

### Out of Scope

Network calls, credentials loading, Shopify SDK, corpus text loading, public schema.

## T02 - Approved External Corpus Reader

### Goal

Load only validated source regions from the approved external corpus into the existing
ephemeral, scope-first controlled retrieval path.

### Why

S09 proves metadata and retrieval behavior but not real source-region loading for an
answerable pilot query. This work can proceed while Shopify credentials are pending.

### Scope

Read-only external source access after manifest, checksum, ordinal, extraction method,
Product scope, language, region, and overlay validation.

### Contract

Internal `ExternalCorpusReader` producing ephemeral scoped retrieval inputs and
existing locator/checksum metadata; raw source text never becomes a repository model,
fixture, log, trace, or persisted artifact.

### Acceptance

- Only approved locator regions are loaded after validation.
- Cross-product, version, checksum, language/region, and overlay mismatches fail before
  retrieval scoring.
- Same input/config replays deterministically.
- Missing evidence returns an exact stop reason without common-knowledge completion.

### Verification

- Unit tests with synthetic minimal text.
- Read-only integration check against approved external corpus metadata/content paths.
- Repository data-boundary scan.

### Dependencies

T01 with corpus lane `GO`.

### Out of Scope

Copying official text into Git, persistent index, embeddings, vector DB, reranker,
multi-product retrieval, training.

## T03 - Real Read-only Shopify Adapter

### Goal

Implement the minimum protocol-independent adapter needed to read current Product,
Variant, price, inventory, and availability for the approved pilot store.

### Why

Dynamic commerce facts cannot be validated using fixtures or staged exports.

### Scope

Injected transport, explicit typed Shopify queries, timeout/attempt budget, response
validation, observed-at capture, error mapping, redaction, and zero-write ledger.

### Contract

Reuse the existing `ShopifyReadPort`, Product/Variant records, `ToolResult`, and
commerce Evidence semantics. No generic operation dispatcher or mutation method.

### Acceptance

- Public surface remains read-only and store-scoped.
- Real responses bind to the requested Product/Variant and preserve `observed_at`.
- Timeout, rate limit, authorization, not-found, malformed response, and identity
  mismatch remain distinguishable.
- Credentials and response payloads are absent from logs, traces, errors, and fixtures.
- Write-call count is zero.

### Verification

- Unit/contract tests with synthetic response bodies.
- Recorded-response integration test only if its metadata contains no secret or private
  Shopify export content.
- One separately authorized live read smoke after all static gates pass.

### Dependencies

T01 with Shopify lane `GO` and explicit Human authorization for external access and
credential use.

### Out of Scope

Shopify mutations, webhook ingestion, pagination framework, cache, background sync,
orders/customers/cart, new public Contract.

## T04 - Pilot Composition Root

### Goal

Wire existing target resolution, application services, Shopify read port, controlled
retrieval, Evidence gate, fallback, trace, and Conversation API into one explicit local
pilot composition.

### Why

Current modules are individually tested but there is no production-like composition
root selecting approved real adapters.

### Scope

Internal configuration validation and explicit `fixture`/`pilot` adapter selection.

### Contract

Reuse `ConversationApplication`, `TurnRequest`, `AnswerEnvelope`, existing internal
ports, and current trace/fallback semantics.

### Acceptance

- Mode is explicit and fail-closed; pilot never silently uses fixture facts.
- Missing readiness, adapter, or configuration prevents startup/turn execution with a
  safe diagnostic.
- No domain decision moves into the FastAPI transport layer.
- Public wire schemas remain unchanged.

### Verification

- Unit tests for mode/configuration selection.
- Integration tests with injected synthetic transports/readers.
- Import, scope, lint, and public-schema diff checks.

### Dependencies

T02 and T03.

### Out of Scope

Deployment configuration, customer auth, durable state, Widget, observability platform,
new Agent framework.

## T05 - Three-product Local Pilot E2E

### Goal

Exercise current dynamic and static facts through the existing Conversation API for
all three approved Products in a local/test pilot.

### Why

The project needs evidence that real-source adapters compose correctly, not another
isolated fixture-only module.

### Scope

The Slice 10 verification matrix, explicit pilot mode, current public request/response,
safe trace, budgets, and zero-write audit.

### Contract

Existing Conversation API, `AnswerEnvelope`, Evidence bindings, fallback semantics,
and `PilotDataReadinessReport`.

### Acceptance

- Each Product passes an identity-bound static or dynamic journey.
- Dynamic facts use only current Shopify results; static facts use only same-Product
  approved corpus evidence.
- Failure paths contain no stale facts, scope mixing, secrets, or internal diagnostics.
- Trace correlation, deadlines, call limits, and zero-write evidence are complete.

### Verification

- Targeted E2E matrix with synthetic transports.
- Separately authorized bounded live-read smoke for the approved store.
- Data/secret boundary scan and Shopify operation-ledger inspection.

### Dependencies

T04 and current-context authorization for the live pilot smoke.

### Out of Scope

Public deployment, real customers, production SLO claim, browser Widget, load test,
model-provider integration.

## T06 - Slice 10 Completion Evidence

### Goal

Consolidate the exact pilot evidence and produce `PILOT_READY_FOR_HUMAN_EVALUATION` or
`HOLD` without claiming production readiness.

### Why

Real-source access must end in an auditable decision before deployment, indexing, or
model work begins.

### Scope

Full Slice 10 matrix, real-source identity/provenance summary, budget results,
data-boundary report, known limitations, and unresolved decisions.

### Contract

Existing Slice workflow evidence plus an internal metadata-only pilot handoff. No new
status platform.

### Acceptance

- Every S10 Acceptance row has actual command/test evidence.
- The handoff accurately distinguishes synthetic verification from live-read evidence.
- No forbidden data, credentials, external writes, Shopify writes, public Contract,
  dependency, or Architecture change is hidden.
- Completion does not authorize production traffic, embeddings/indexing, training, or
  push.

### Verification

- Full project suite once at Slice completion.
- Slice 10 scope, data-boundary, dependency, public-contract, and secret scans.
- One final independent read-only Slice review after a completion snapshot.

### Dependencies

T05.

### Out of Scope

Production release, PR/push, deployment, Golden Set freeze, production index, future
Slice implementation.

## Human Escalation Conditions

Stop on any condition listed in `plan.md`, especially public Contract or Architecture
change, new runtime dependency, mutation-capable Shopify access, unresolved Variant
identity, corpus authorization change, forbidden data copy, production traffic, or
model-generated facts.

## Recommended Next Step

Create the approved planning baseline, then configure and review only the minimum S10
Workflow Policy. Do not execute T01 before policy activation and the applicable
implementation authority.
