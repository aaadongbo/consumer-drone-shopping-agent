# Slice 11 Tasks - Closed-beta Deployment and Release

> Status: IMPLEMENTATION IN PROGRESS / S11 AUTHORIZED / T03 DONE, REVIEW PENDING
>
> The ordered table below is a planning proposal only. It does not authorize
> implementation, external service use, credential access, CI changes, deployment,
> push, merge, or closed-beta traffic.

## Ordered Tasks

| Task | Title | Status | Dependencies |
|---|---|---|---|---|
| T01 | Deployment readiness reconciliation | DONE | S10 completion evidence; Human accepts S11 planning baseline |
| T02 | Production-like composition and config boundary | DONE | T01 |
| T03 | Health, error, CORS, and security guardrails | DONE | T02 |
| T04 | Model or restricted intent adapter boundary | NOT_STARTED | T02; Human provider/model ID decision if live model is used |
| T05 | Embeddable Storefront Widget | NOT_STARTED | T02, T03; exact staging/beta Widget origin values |
| T06 | CI, staging deployment, and rollback path | NOT_STARTED | T03, T05; exact hosting vendor, staging URL, Secret Store, and rollback operator |
| T07 | Closed-beta acceptance and completion evidence | NOT_STARTED | T04, T06; explicit live smoke authority |

| Task | Risk |
|---|---|
| T01 | LOW |
| T02 | MEDIUM |
| T03 | MEDIUM |
| T04 | HIGH |
| T05 | MEDIUM |
| T06 | HIGH |
| T07 | MEDIUM |

Risk labels are provisional planning labels. HIGH Tasks stop for current-context Human
authority before implementation because they involve external providers, release
infrastructure, security posture, or production-like traffic boundaries.

## T01 - Deployment Readiness Reconciliation

### Goal

Turn the S10 local pilot completion handoff into a metadata-only release-readiness
report for S11.

### Why

Deployment work is unsafe unless the remaining decisions, data boundary, DEC-012
status, and three-product pilot limitations are explicit.

### Scope

Planning and read-only inspection of S10 evidence, current core artifacts, existing
runtime files, existing tests, and any already-present deployment/CI files.

### Contract / Inputs and Outputs

Input: S10 completion evidence, core docs, current repository state, and S11 plan.
Output: internal `RuntimeReadinessReport` draft or Markdown reconciliation note with
`GO`/`HOLD` lanes for single-container host vendor, hosted Secret Store, local macOS
Keychain, Shopify read credential, explicit Widget origins, deterministic
interpreter/model adapter, GitHub Actions checks, staging, rollback, DEC-012, and
data boundary.

### Acceptance

- Report states that S11 is closed beta only and uses exactly the approved three
  Products.
- Every open decision in `plan.md` is classified as decided, baseline-accepted, or
  `HOLD`.
- Missing exact host vendor, Secret Store, staging URL, rollback operator, model
  provider/model ID, or Widget-origin value blocks implementation of dependent Tasks.
- DEC-012 is recorded as `ACCEPTED` in `docs/DECISIONS.md`; dependent Tasks must not
  change that content boundary.
- No Product Behavior, Architecture, public Contract, dependency, or business code is
  changed.

### Verification

- Markdown/diff review.
- `git status --short` confirms only `docs/DECISIONS.md` and authorized S11 planning
  artifacts changed.
- Optional targeted doc-link check if available.

### Dependencies

S10 completion evidence and Human acceptance of the S11 planning baseline.

### Out of Scope

Implementation, deployment files, credentials, `.env` files, external network calls,
CI setup, Widget code, public Contract changes, and Slice 12.

## T02 - Production-like Composition and Config Boundary

### Goal

Add the minimal runtime composition and typed config validation needed to start the
existing pilot path in explicit closed-beta mode.

### Why

The beta must not rely on implicit local fixtures, missing env defaults, or ambiguous
adapter selection.

### Scope

Startup command, release-mode selection, required environment keys, safe defaults,
hosted Secret Store references, local macOS Keychain references, adapter wiring,
request/time/tool/model budgets, and fail-closed config diagnostics.

### Contract / Inputs and Outputs

Input: environment variables and injected secret references. Output: validated
`ReleaseConfig`, explicit composition mode, and safe startup/readiness failure when
config is incomplete.

### Acceptance

- `closed_beta` startup never silently uses fixture adapters or stale pilot snapshots.
- Missing required env, hosted Secret Store reference, local Keychain reference,
  explicit origin, or model/intent settings fail closed before serving beta traffic.
- Config exposes provisional budget keys from `plan.md` with hard limits.
- Secret values and `.env` files are never serialized to responses, logs, trace, test
  fixtures, or committed files.
- Existing public request/response schema remains unchanged unless Human accepts a
  versioned Contract proposal.

### Verification

- Unit tests for valid, missing, malformed, and unsafe config.
- Integration startup checks using injected fake secrets/adapters.
- Secret-string and forbidden-artifact scan over changed files.
- Targeted lint/format checks for touched code.

### Dependencies

T01 with required lanes decided or explicitly held safe.

### Out of Scope

Hosted deployment, real credentials, database/cache introduction, health endpoints,
Widget code, CI changes, external calls, public launch.

## T03 - Health, Error, CORS, and Security Guardrails

### Goal

Implement minimum release guardrails around liveness/readiness, CORS, rate/concurrency
limits, safe errors, redacted logs, trace correlation, and zero-write ledgers.

### Why

Closed beta still needs predictable failure behavior and audit evidence before any
external user can touch the system.

### Scope

Metadata-only health/readiness, explicit staging/beta CORS allowlist, in-process
provisional rate limits, per-session concurrency, redaction policy, safe exception
mapping, operation counters, and no-secret/no-raw-payload checks.

### Contract / Inputs and Outputs

Input: `ReleaseConfig`, request metadata, adapter operation records, and trace events.
Output: safe health/readiness status, stable rate-limit/fallback responses, redacted
logs/traces, and `OperationLedger` with Shopify writes equal to zero.

### Acceptance

- Health/readiness finishes within `health_timeout_ms` and contains no secrets,
  payloads, raw Shopify responses, or official source text.
- Only configured staging/beta Widget origins are accepted; wildcard and unapproved
  origins fail in tests.
- Rate and concurrency limits produce stable retry/fallback semantics.
- Error paths do not expose stack traces, headers, tokens, secrets, raw protected data,
  or internal diagnostics to users.
- Shopify write count remains `0` across tested paths.

### Verification

- Unit tests for health, readiness, redaction, and rate/concurrency boundaries.
- Contract/integration tests for CORS and safe error responses.
- Operation-ledger tests proving no write methods are present or called.
- Targeted data/secret boundary scan.

### Dependencies

T02.

### Out of Scope

Full observability platform, external monitoring service, SIEM/APM, Redis-backed rate
limits, distributed locking, Shopify writes, customer auth, staging deployment.

## T04 - Model or Restricted Intent Adapter Boundary

### Goal

Wire the deterministic interpreter fallback and the minimum replaceable model/intent
adapter required for closed-beta journeys.

### Why

The beta needs enough language understanding for approved journeys, but model behavior
must remain bounded and unable to invent product facts or bypass Evidence gates.

### Scope

Deterministic fallback, replaceable adapter boundary, optional provider/model ID,
timeout/token/tool budgets, low-confidence handling, fallback semantics, prompt/config
redaction, and deterministic test doubles.

### Contract / Inputs and Outputs

Input: user turn, current state, approved route/intent context, and budget config.
Output: bounded intent/route signal or safe fallback. The adapter does not produce
commerce/document truth, alter Product/Variant identity, change HARD constraints, or
override Evidence gates.

### Acceptance

- Deterministic interpreter fallback and replaceable adapter semantics are preserved;
  live provider/model ID remains an open Human decision.
- Timeout, provider failure, low confidence, unsupported intent, and budget exhaustion
  return safe fallback without invented facts.
- CI uses deterministic fakes and does not require live model access.
- Real-model smoke, if authorized, records metadata only and no prompt secrets,
  protected source text, or raw response payloads.
- No public Contract, Product Behavior, or Architecture boundary changes occur without
  separate Human approval.

### Verification

- Unit/contract tests with deterministic fakes.
- Budget and fallback tests for timeout, low confidence, provider failure, unsupported
  intent, and token limit.
- Redaction and no-secret scans.
- Optional separately authorized live provider smoke after static gates pass.

### Dependencies

T02 and current-context Human decision for provider/model ID before any live model
adapter or smoke.

### Out of Scope

Fine-tuning, training data, autonomous Agent framework, open-web search, unrestricted
tool calls, model-generated product facts, CI dependency on live provider.

## T05 - Embeddable Storefront Widget

### Goal

Build the minimum Shopify-storefront embeddable Widget for approved closed-beta
journeys.

### Why

S11 must validate the actual beta entry point, not only backend APIs or local harnesses.

### Scope

Widget embed config, approved backend endpoint, product/variant page context mapping,
send/retry/reset controls, loading/progressive/final answer states, target display,
constraint chips, evidence/freshness display, fallback action, and safe client-side
error handling.

### Contract / Inputs and Outputs

Input: `WidgetEmbedConfig`, explicit staging/beta origin allowlist, current page
Product/Variant context, user message, and existing Conversation API response
semantics. Output: rendered closed-beta chat interaction that calls only the
Conversation API and contains no credentials or business logic in the browser.

### Acceptance

- Widget can be embedded only on explicit staging/beta storefront origin(s) without
  exposing secrets or permitting wildcard CORS.
- It sends current page context and renders the existing final response schema.
- Target display, evidence, freshness, fallback, loading, retry, reset, and error
  states are visible for approved beta journeys.
- Widget does not perform product eligibility, recommendation ranking, Shopify API
  access, direct non-Conversation API calls, or Evidence validation client-side.
- UI failure paths are safe and do not leak internal diagnostics.

### Verification

- Unit/component tests for state rendering and response mapping.
- Browser or E2E smoke for desktop/mobile approved viewports if the frontend stack
  supports it.
- CORS integration check against T03.
- Build/lint checks for touched Widget files.

### Dependencies

T02, T03, and exact staging/beta Widget origin values for `OD-S11-05`.

### Out of Scope

Theme write/deploy automation, public app distribution, analytics suite, checkout/cart
actions, multi-language UI, customer auth, complex design system, Shopify writes.

## T06 - CI, Staging Deployment, and Rollback Path

### Goal

Create the Human-approved release path: required CI checks, staging deployment, access
control, smoke command, and rollback procedure.

### Why

Closed beta should be releasable and reversible with auditable gates, not manually
assembled from local commands.

### Scope

GitHub Actions check definitions, staging config, single-container deployment command
or manifest, access-control notes, smoke-test entry points, release checklist, and
one-command rollback procedure.

### Contract / Inputs and Outputs

Input: selected single-container hosting vendor, GitHub Actions required check names,
hosted Secret Store, staging URL, rollback target/operator, immutable commit/image
strategy, and S11 acceptance matrix. Output: a staging release candidate with required
checks and a documented one-command rollback path.

### Acceptance

- Human has approved exact hosting vendor, staging URL, Secret Store, required check
  names, rollback operator, and immutable commit/image strategy before coding.
- Required GitHub Actions checks block release on lock, Ruff, unit, contract,
  integration, build, config validation, data-boundary, Widget, and smoke-test
  failures.
- Staging smoke verifies startup, readiness, explicit-origin CORS, Widget, redacted
  logs, no-write ledger, and one real read-only three-product journey before beta
  traffic.
- Rollback restores the previous known-good immutable commit/image or disables beta
  traffic fail-closed through one command within the approved window, with no database
  migration.
- No public launch, production SLO, or open beta traffic is authorized.

### Verification

- GitHub Actions dry-run or local equivalent where supported.
- Staging smoke with explicit Human authority.
- Rollback rehearsal or documented no-traffic disable path.
- Diff review for no secrets, raw protected data, or unauthorized infrastructure.

### Dependencies

T03, T05, and exact Human decisions for host vendor, GitHub Actions check names,
staging URL, Secret Store, immutable commit/image strategy, and rollback operator.

### Out of Scope

Kubernetes, multi-region HA, blue/green platform automation beyond the approved host,
full monitoring stack, public traffic, auto-merge, direct protected-branch push.

## T07 - Closed-beta Acceptance and Completion Evidence

### Goal

Consolidate all S11 evidence and report whether the Slice is ready for Human closed
beta release decision.

### Why

Deployment readiness must end in a reviewable evidence bundle with exact scope,
commands, operation counts, staging status, rollback status, and data boundaries.

### Scope

Full S11 acceptance matrix, three-product real read-only staging smoke, redacted-log
evidence, rollback evidence, required GitHub Actions result, data/secret scan,
operation ledger, known limitations, open decisions resolved or deferred, and final
Slice review handoff.

### Contract / Inputs and Outputs

Input: Task evidence, command results, staging metadata, no-write ledger, and final
diff. Output: `CLOSED_BETA_READY_FOR_HUMAN_RELEASE_DECISION` or `HOLD` with exact
blocking reasons.

### Acceptance

- Every `S11-Axx` acceptance row has actual PASS/FAIL evidence.
- The real three-product smoke uses approved read-only data and records metadata only.
- Shopify write count is `0`; no secret, raw Shopify payload, official full text,
  chunk, index, embedding, Golden Set label, or training data is committed.
- GitHub Actions, staging smoke, Widget smoke, config fail-closed, explicit-origin
  CORS, rate-limit/error safety, redacted logs, model/intent fallback, and rollback
  evidence are complete.
- Completion does not claim public launch, production scale, Human release approval,
  integration, merge, push, or Slice 12.

### Verification

- Full project suite once at Slice completion.
- Required CI or local equivalent evidence.
- Data/secret boundary scan.
- Staging and rollback smoke evidence with real exit codes/results.
- Final independent Slice review on an immutable completion snapshot.

### Dependencies

T04, T06, and explicit authority for live read-only smoke and staging checks.

### Out of Scope

Human release approval, public launch, production traffic expansion, main integration,
merge, push, roadmap planning, or any post-beta implementation.

## Human Escalation Conditions

Stop on any condition listed in `plan.md`, especially Product Behavior, Architecture,
public Contract, Accepted Decision, major dependency, external service, Shopify write,
security boundary, production traffic, rollback policy, credential, real model
provider, hosting, CI, staging, or Widget-origin changes.

## S11-T01 Execution Record

- **Status**: `DONE`
- **Start commit**: `c612f27e73b3b69bce555ba5349e1a1a89c78c95`
- **Start worktree**: clean; no staged or untracked files before T01.
- **Authorization**: current-context S11 implementation authorization with the exact
  approved Workflow Policy baseline `c612f27e73b3b69bce555ba5349e1a1a89c78c95`.
- **Boundary**: metadata-only reconciliation of S10 handoff, S11 planning baselines,
  DEC-012 status, open decisions, data boundary, and existing runtime/deployment
  surface. No business code, tests, dependency, external-service, credential, or
  deployment change is permitted.
- **Readiness result**: `GO` for the bounded S11 planning baseline and `HOLD` for
  dependent implementation lanes whose exact host vendor, Secret Store, staging/beta
  origins, rollback operator, or model provider/model ID remains unresolved.
- **Evidence**: S10 handoff is `PILOT_READY_FOR_HUMAN_EVALUATION`; DEC-012 is
  `ACCEPTED`; the approved three-product/read-only boundary and no-Slice-12 boundary
  are recorded in the plan. No public Contract, Architecture, dependency, or
  external-service behavior changed.
- **Verification**:
  - `git status --short --branch` exited `0`; only this Task record was dirty.
  - `git diff --check` exited `0`.
  - `rg` checks for the S10 handoff, DEC-012, approved S11 baselines, open decisions,
    and no-Slice-12 boundary exited `0`.
  - `inspect_state.py --authorize-slice S11 --approved-workflow-oid
    c612f27e73b3b69bce555ba5349e1a1a89c78c95` resolved `S11-T01` as the selected
    boundary with no dependency blocker; the current Task record itself remained the
    only working-tree change.
- **Known limits**: T01 does not select a hosting vendor, Secret Store, model
  provider, Widget origin, staging URL, rollback operator, or live external-service
  authority. Those decisions remain explicit gates for T02/T04/T05/T06/T07.

## Pre-T02 Data Readiness Reconciliation

- **Status**: `CANDIDATE_NOT_GOLDEN`; external Data-Staging artifact only.
- **Dataset path**:
  `/Users/russeell/Documents/Data-Staging/consumer-drone-agent/outputs/seed-synthetic-query-set-20260905-v0.1-candidate/`
- **Purpose**: prepare a seed/synthetic query set for later S11 closed-beta data
  readiness review without executing `S11-T02`, changing business code, changing
  public Contracts, or authorizing deployment/runtime implementation.
- **Scope**: exactly the approved three Products and three observed Variant IDs from
  `shopify-dji-snapshot-20260831-v0.3` plus
  `shopify-adapter-smoke-20260905-v0.4` metadata. Raw query text remains external to
  Git; Git-visible planning records only path, status, count, coverage, and sidecar
  boundary.
- **Coverage**: pronoun/contextual turns, Product/Variant identity, price, inventory,
  specifications, packaging, cross-product comparison, recommendation, after-sales,
  ambiguity, unverifiable claims, wrong-scope, zero-hit, English, Chinese colloquial
  phrasing, and typo cases.
- **Boundary**: no secret, token, `.env`, full Shopify response, official full text,
  chunk, index, embedding, Golden Set label, training data, Shopify write, network
  call, dependency, Workflow, Architecture, Product Behavior, or public Contract
  change is introduced.
- **Authority**: this reconciliation did not activate or execute `S11-T02`; the
  formal Task status is tracked in the execution record below.

## S11-T02 Execution Record

- **Status**: `DONE`
- **Start commit**: `5eefc0341940d8681c663efc0382e0b6058386ba`
- **Start worktree**: clean; no staged or untracked files before T02.
- **Authorization**: current-context S11 implementation authorization with the exact
  approved Workflow Policy baseline `c612f27e73b3b69bce555ba5349e1a1a89c78c95`.
- **Boundary**: internal typed runtime configuration and explicit composition boundary
  only; no public Contract, external service, credential, deployment, or dependency
  change.

### T02 Completion Record

- **Status**: `DONE — MEDIUM Review PASS / AUTO_ADVANCE_ELIGIBLE`
- **Changed paths**: `backend/runtime/config.py`, `backend/runtime/composition.py`,
  `backend/runtime/__init__.py`, `tests/unit/test_s11_t02_runtime_config.py`, and
  this Task record.
- **Acceptance**: explicit `closed_beta`/`single_container` settings, read-only pilot
  adapter selection, local Keychain versus hosted Secret Store references, explicit
  non-wildcard Widget origins, deterministic/provider intent modes, provisional hard
  budgets, safe metadata diagnostics, and fixture-fallback rejection are implemented.
- **Verification**:
  - `uv run ruff check backend/runtime tests/unit/test_s11_t02_runtime_config.py`
    exited `0`.
  - `uv run ruff format --check backend/runtime tests/unit/test_s11_t02_runtime_config.py`
    exited `0`.
  - `uv run pytest -m unit tests/unit/test_s11_t02_runtime_config.py -q` exited `0`
    (`10 passed`).
  - Independent child review re-ran immutable evidence, targeted lint/format,
    targeted tests, and diff checks; all exited `0`, with `AI_REVIEW_PASS` and
    an empty findings list.
  - No Shopify/network call was made; the test transport raises if invoked.
- **Known limits**: hosting vendor, hosted Secret Store product, live model provider,
  Widget origins, deployment, CI, health endpoints, and external credentials remain
  explicit later-Task decisions; no public Contract or dependency was changed.
- **Recommended next Task**: continue with `S11-T03`.

## S11-T03 Execution Record

- **Status**: `DONE — Awaiting MEDIUM Task Review`
- **Start commit**: `182d51785ed20406cbf1f17c6d7dd0af1e6c0f86`
- **Start worktree**: clean; no staged or untracked files before T03.
- **Authorization**: current-context S11 implementation authorization with the exact
  approved Workflow Policy baseline `c612f27e73b3b69bce555ba5349e1a1a89c78c95`.
- **Boundary**: in-process health/readiness, explicit-origin CORS, safe exception
  responses, metadata-only redaction, rate/concurrency limits, and read-only
  operation counters. No public Contract, dependency, external service, Shopify
  write, deployment, or persistent state change.
- **Changed paths**: `backend/runtime/guardrails.py`, `backend/runtime/__init__.py`,
  `backend/api/guardrails.py`, `backend/api/__init__.py`,
  `tests/unit/test_s11_t03_guardrails.py`,
  `tests/contract/test_s11_t03_guardrails_contract.py`,
  `tests/integration/test_s11_t03_guardrails_api.py`, and this Task record.
- **Acceptance**: health reports contain only safe metadata and fail closed on
  readiness; CORS accepts only exact configured origins; rate and concurrency
  limits are bounded and stable; unexpected errors expose no diagnostics; logs
  redact secrets/payloads; and the operation ledger has no write surface and a
  zero write-call count.
- **Verification**:
  - Initial Ruff check reported one unused import, duplicate exports, and formatting
    findings; the minimal mechanical fixes were applied.
  - Initial CORS integration assertion exposed a method-list mismatch; `GET` was
    added to the explicitly allowlisted methods and the regression passed.
  - `uv run ruff check backend/runtime backend/api/guardrails.py
    tests/unit/test_s11_t03_guardrails.py
    tests/contract/test_s11_t03_guardrails_contract.py
    tests/integration/test_s11_t03_guardrails_api.py` exited `0`.
  - `uv run ruff format --check backend/runtime backend/api/guardrails.py
    tests/unit/test_s11_t03_guardrails.py
    tests/contract/test_s11_t03_guardrails_contract.py
    tests/integration/test_s11_t03_guardrails_api.py` exited `0`.
  - `uv run pytest -m 'unit or contract or integration' ...` exited `0`
    (`16 passed`). Unit-only and integration-only reruns also exited `0`
    (`12 passed` and `2 passed`).
- **Known limits**: rate/concurrency state is intentionally process-local; external
  monitoring, distributed limits, deployment, and production traffic remain out of
  scope. T03 does not alter the public wire Contract.
- **Recommended next Task**: create the immutable T03 MEDIUM snapshot and complete
  its independent read-only review before considering `S11-T04`.
