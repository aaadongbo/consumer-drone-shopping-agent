# Slice 10 Tasks - Real-data Read-only Pilot

> Status: IMPLEMENTATION AUTHORIZED / Formal Slice Task Table
>
> Human has accepted the Slice 10 goal, scope, acceptance, provisional budgets, and
> ordered Task table. The formal rows below are `NOT_STARTED`; this does not by itself
> authorize live credentials, external network access, push, or production use.

## Ordered Tasks

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Pilot identity and data-readiness gate | DONE | S09 locally integrated; S10 planning approval |
| T02 | Approved external corpus reader | DONE | T01 corpus lane `GO` |
| T03 | Real read-only Shopify adapter | NOT_STARTED | T01 Shopify lane `GO`; explicit external-access authorization |
| T04 | Pilot composition root | NOT_STARTED | T02, T03 |
| T05 | Three-product local pilot E2E | NOT_STARTED | T04 |
| T06 | Slice 10 completion evidence | NOT_STARTED | T05 |

Risk labels and execution cadence are defined by the activated S10 Workflow Policy.
They are not external-service authority. T03 and T05 remain explicit Human
boundaries because they involve real credentials/network behavior and real-source E2E.

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

## S10-T01 Execution Record

- **Status**: `DONE`
- **Start commit**: `a58b6e8979ec89d1f5a85e20786b57f570f7b9f6`
- **Start worktree**: clean; no staged or untracked files before implementation.
- **Authorization**: current-context Slice 10 authorization with approved Workflow
  baseline `a58b6e8979ec89d1f5a85e20786b57f570f7b9f6`.
- **Boundary**: internal metadata-only readiness; no Shopify network, credentials,
  external corpus content, Data-Staging writes, public Contract, or dependency.
- **Baseline verification**:
  - `uv run pytest -q` first failed with uv cache permission (`exit 2`); no tests ran.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run pytest -q` exited `0`
    with `621 passed in 0.78s`.
- **Implementation**: Added internal-only `PilotDataReadinessReport`, separate
  Shopify/corpus lane reports, stable Product/Variant identity validation, and safe
  metadata serialization. Missing read-only credential, unresolved/duplicate/foreign
  identity, missing corpus metadata, and missing chunk baseline all fail closed as
  lane-specific `HOLD` reasons. No network, credentials, source text, Data-Staging
  write, public Contract, or dependency was introduced.
- **Targeted verification**:
  - `PYTHONDONTWRITEBYTECODE=1 python -c "...compile..."` exited `0`.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run ruff check
    backend/catalog/pilot_readiness.py backend/catalog/__init__.py
    tests/unit/test_s10_t01_pilot_readiness.py
    tests/contract/test_s10_t01_readiness_contract.py` exited `0`.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run ruff format --check
    ...` exited `0`.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run pytest -m 'unit or
    contract' tests/unit/test_s10_t01_pilot_readiness.py
    tests/contract/test_s10_t01_readiness_contract.py -q` exited `0` with `7 passed`.
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py S10-T01`
    exited `0` with no disallowed, core-artifact, dependency, or semantic data paths.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S10-T01`
    exited `0`; syntax, Ruff, format, targeted tests, diff, core-artifact, and
    dependency gates passed.
- **Readiness result**: The repository implementation is ready for metadata input;
  the current default external lanes remain `HOLD` until approved identity,
  read-only credential metadata, corpus metadata, and corrected chunk baseline are
  supplied. No external access was attempted.
- **Read-only Data-Staging metadata check**:
  - The admitted `rag-corpus-20260902-v0.1` manifest reports three products and
    `chunks=0`, `embeddings=0`, `indexes=0`, `retrieval_runs=0`.
  - The corrected `rag-chunking-ablation-20260902-v0.3/manifest.json` is absent and
    its review sidecar is `AI_REVIEW_NEEDS_CHANGES`; the corpus lane therefore cannot
    become `GO`.
  - The Shopify v0.3 candidate review confirms three Product IDs but
    `variant_id_status=UNRESOLVED_FROM_STANDARD_EXPORT`; Variant IDs are explicitly
    unresolved before real adapter smoke or implementation ingestion. Shopify lane
    therefore remains `HOLD`.
  - These checks read metadata only; no PDF, source text, export row, credential,
    network endpoint, or staging file was opened or written.
- **Recommended Next Task**: `S10-T02` is dependency-ready but remains `NOT_STARTED`;
  it requires a corpus lane `GO` and any external corpus access remains an explicit
  Human boundary.

## Recommended Next Step

The S10 Workflow Policy is activated separately. Do not execute T01 before the
current-context implementation authority and the applicable data-readiness checks.

## S10-T02 Execution Record

- **Status**: `DONE`
- **Start commit**: `beefd90a8e7600db50510c5a6ae57f32f8f853c6`
- **Start worktree**: clean; no staged or untracked files before implementation.
- **Authorization**: current-context Slice 10 implementation authorization; selected
  by `inspect_state.py --authorize-slice S10` as executable `S10-T02`.
- **Boundary**: internal read-only external corpus reader; no repository fixture raw
  source text, PDF, chunk body, embedding, index, secret, dependency, public Contract,
  or Data-Staging write was introduced.
- **Implementation**: Added `ExternalCorpusReader`, `PdfPageTextRegionLoader`, typed
  fail-closed stop reasons, injected `SourceRegionLoader`, and text-free
  `safe_metadata()`. The reader validates corpus readiness metadata, corrected chunk
  manifest acceptance, corpus-manifest checksum, source-inventory checksum,
  scope-first controlled retrieval, source-region availability, UTF-8 decoding, and
  per-region `text_sha256` before creating ephemeral in-memory `DocumentChunk`
  retrieval inputs. `pdftotext` is used only by the default local PDF loader and
  captured output is not logged.
- **Read-only external check**: The integration smoke read the approved
  `/Users/russeell/Documents/Data-Staging/consumer-drone-agent/outputs/rag-corpus-20260902-v0.1`
  corpus and approved
  `/Users/russeell/Documents/Data-Staging/consumer-drone-agent/outputs/rag-corrected-chunk-baseline-20260905-v0.1/corrected-chunk-baseline.manifest.json`
  manifest. It selected the DJI Air 3 `下载调参软件` locator, extracted that PDF page to
  memory with `pdftotext`, and matched the corrected manifest checksum. No raw text was
  printed, committed, persisted, or written to Data-Staging.
- **Targeted verification**:
  - `PYTHONDONTWRITEBYTECODE=1 python -m py_compile
    backend/rag/external_corpus_reader.py
    tests/unit/test_s10_t02_external_corpus_reader.py
    tests/integration/test_s10_t02_external_corpus_reader.py` exited `0`.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run ruff check --fix
    backend/rag/__init__.py` exited `0`; one import-order issue fixed.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run ruff check
    backend/rag/external_corpus_reader.py backend/rag/__init__.py
    tests/unit/test_s10_t02_external_corpus_reader.py
    tests/integration/test_s10_t02_external_corpus_reader_live.py` exited `0`.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run ruff format --check
    backend/rag/external_corpus_reader.py backend/rag/__init__.py
    tests/unit/test_s10_t02_external_corpus_reader.py
    tests/integration/test_s10_t02_external_corpus_reader_live.py` exited `0`.
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run pytest -m 'unit or
    integration' tests/unit/test_s10_t02_external_corpus_reader.py
    tests/integration/test_s10_t02_external_corpus_reader_live.py -q` exited `0` with
    `6 passed`.
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py S10-T02`
    exited `0` with no disallowed, core-artifact, dependency, forbidden-slice, or
    semantic-action violations.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S10-T02`
    exited `0`; syntax, Ruff, format, targeted tests, diff whitespace, core-artifact,
    and dependency gates passed.
- **Known limit**: T02 does not authorize or perform Shopify access. The LOW batch
  stop reason after T02 is the non-LOW/external boundary at `S10-T03`.
