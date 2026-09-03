# Slice 8 Tasks - Data-backed Product RAG Readiness

> Status: APPROVED IMPLEMENTATION BASELINE / NOT_STARTED
>
> Human has accepted this Task table, and S08 Workflow Policy exists for fail-closed
> execution routing. The table below uses formal Task states; `NOT_STARTED` does not
> by itself authorize implementation, snapshot, commit, push, external-service access,
> Data-Staging mutation, embeddings, indexes, or training. Start S08-T01 only after
> separate current-context implementation authority.

## Ordered Tasks

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | External corpus readiness adapter | NOT_STARTED | Human Review + planning baseline |
| T02 | Locator and scope binding gate | NOT_STARTED | T01 |
| T03 | Offline single-target retrieval walking skeleton | NOT_STARTED | T02 |
| T04 | Static/dynamic fallback and stale-data guards | NOT_STARTED | T03 |
| T05 | Data boundary and no-upload verification | NOT_STARTED | T04 |
| T06 | Slice readiness evidence and Human handoff | NOT_STARTED | T05 |

## S08-T01 - External Corpus Readiness Adapter

- **Goal**: Build a repository-local adapter/readiness report that reads only approved
  external staging metadata paths and validates the RAG corpus v0.1 manifest shape.
- **Why**: S08 needs a safe bridge from Data-Staging into existing internal RAG
  semantics without copying source PDFs or treating the corpus as indexed.
- **Scope**: `rag-corpus-20260902-v0.1/manifest.json`, source inventory, derived
  locator file paths, decision bindings, checksum/count fields, and status values.
- **Contract**: Internal `CorpusReadinessReport` with manifest path/checksum,
  corpus_version, counts, decision bindings, accepted/rejected files, and exact stop
  reason.
- **Acceptance**: Valid corpus v0.1 reports admitted sources and 261 locators, but
  also reports `CORPUS_NOT_INDEXED`; missing manifest/checksum/status mismatch fails
  closed.
- **Verification**: Unit tests for valid manifest, missing manifest, bad checksum,
  wrong status, and no-index counts; no Data-Staging writes.
- **Dependencies**: Human-approved S08 planning baseline; no S08 workflow policy unless
  separately approved.
- **Out of Scope**: Chunk generation, embeddings, index creation, retrieval serving,
  public schema changes, Data-Staging mutation, Shopify access, training.

## S08-T02 - Locator and Scope Binding Gate

- **Goal**: Validate that every candidate locator binds to one source, version, page,
  product scope, language, region, and overlay decision before it can become Evidence.
- **Why**: Current corpus readiness depends on page-level locator correctness and
  Mavic 3/Cine exclusion, not on model trust.
- **Scope**: Page locator JSONL records from corpus v0.1, `mavic_3_scope_overlay.v0.1`,
  and existing `ObjectScope` / `SourceLocator` semantics.
- **Contract**: Internal `LocatorBinding` plus rejection reasons for product, variant,
  language, region, source, version, checksum, page, and overlay mismatch.
- **Acceptance**: Mini 3, Air 3, and Mavic 3 locators pass only in their own target
  scope; cross-product injection and Mavic 3/Cine overlay hits are rejected.
- **Verification**: Focused unit/contract tests with small metadata-only fixtures;
  no copied official text or raw PDFs in fixtures.
- **Dependencies**: S08-T01.
- **Out of Scope**: Multi-product comparison/recommendation allocation, generated
  answers, client rendering, Golden Set freeze.

## S08-T03 - Offline Single-target Retrieval Walking Skeleton

- **Goal**: Create the smallest offline single-target retrieval/readiness skeleton
  that can return scoped candidate locators or abstain with a stop reason.
- **Why**: Existing S05 Product RAG is in-memory and synthetic; S08 should prove that
  real staged metadata can pass through the same one-target boundary before any index.
- **Scope**: One resolved Turn Target, metadata-first filtering, deterministic scoring
  or lookup over metadata-only test fixtures, `max_scoped_candidates=10`, and existing
  bounded budget defaults.
- **Contract**: Reuse existing `RetrievalRequest`/`RetrievalResult` semantics where
  possible; add only internal stop reasons if needed.
- **Acceptance**: Static manual-style questions return same-product candidate locators
  only when metadata is valid; no scoped candidate returns `NO_SCOPED_MATCH` or
  `CORPUS_NOT_INDEXED` as appropriate.
- **Verification**: Integration tests for Mini 3/Air 3/Mavic 3 scoped candidates,
  cross-product rejection, budget limit, and deterministic replay.
- **Dependencies**: S08-T02.
- **Out of Scope**: BM25/vector service, embeddings, reranker, live model generation,
  open-web search, multi-agent framework.

## S08-T04 - Static/Dynamic Fallback and Stale-data Guards

- **Goal**: Ensure static RAG never answers dynamic Shopify facts and candidate
  Shopify snapshots cannot masquerade as current truth.
- **Why**: DEC-009 is accepted, and Shopify v0.3 remains a candidate with limitations.
- **Scope**: Price, inventory, availability, current sale status, Shopify Variant ID
  uncertainty, corpus version mismatch, chunking review `AI_REVIEW_NEEDS_CHANGES`,
  and unfrozen eval/training states.
- **Contract**: Exact fallback/stop reasons including `DYNAMIC_FACT_REQUIRED`,
  `CHUNK_BASELINE_NEEDS_CHANGES`, `GOLDEN_SET_NOT_FROZEN`, and
  `TRAINING_NOT_AUTHORIZED`.
- **Acceptance**: Dynamic-commerce questions never use RAG corpus or staging snapshots;
  missing/invalid chunk baseline blocks integration; eval/training artifacts cannot be
  promoted accidentally.
- **Verification**: Contract tests for dynamic fact questions, Shopify v0.3 unresolved
  Variant ID, missing chunk manifest, `AI_REVIEW_NEEDS_CHANGES`, and Golden Set not
  frozen.
- **Dependencies**: S08-T03.
- **Out of Scope**: Live Shopify OAuth/smoke, commerce refresh implementation, SKU
  repair, new Shopify exports, training dataset generation.

## S08-T05 - Data Boundary and No-upload Verification

- **Goal**: Add explicit verification that repository changes do not include raw PDFs,
  official document text, Shopify exports, staging outputs, embeddings, indexes,
  secrets, or training files.
- **Why**: User constraints forbid uploading datasets/official materials to
  `russeell` GitHub and forbid copying raw PDFs or training data into the public repo.
- **Scope**: Repository diff/path checks, fixture content checks, zero-write audit, and
  command evidence that no remote Git or Shopify write operation ran.
- **Contract**: Verification report or test helper scoped to S08 paths and no-upload
  forbidden patterns.
- **Acceptance**: Any forbidden artifact in repo diff fails verification; allowed
  fixtures are metadata-only and small; no Data-Staging write calls are made.
- **Verification**: Targeted tests plus `git status --short`, forbidden path/content
  scan, and command log review for zero writes.
- **Dependencies**: S08-T04.
- **Out of Scope**: Pushing, PR creation, repository hosting changes, Data-Staging
  cleanup, deleting external artifacts.

## S08-T06 - Slice Readiness Evidence and Human Handoff

- **Goal**: Collect S08 completion evidence for the planning-to-implementation
  boundary and hand off remaining decisions without claiming Human approval.
- **Why**: S08 should close as a readiness/control Slice, not silently proceed to
  embedding, serving, Golden Set freeze, or training.
- **Scope**: Verification matrix replay, changed-path summary, staging references,
  open decisions, known blockers, and next-step recommendation.
- **Contract**: Existing Slice workflow evidence style only; no new status platform.
- **Acceptance**: All S08 acceptance rows have actual test/command evidence, no
  forbidden data entered the repo, and open decisions remain explicitly deferred.
- **Verification**: Targeted S08 tests, relevant existing RAG/contract tests, no-upload
  scan, `git status --short`, and workflow scope/readiness checks if a policy exists.
- **Dependencies**: S08-T05.
- **Out of Scope**: Snapshot/commit/push/integration unless separately authorized,
  Human approval claims, S09 planning, production RAG serving.

## Verification Matrix

| Task | Required verification |
|---|---|
| S08-T01 | Manifest/readiness unit tests; valid corpus v0.1, missing manifest, wrong status, checksum/count mismatch. |
| S08-T02 | Locator binding tests; product/language/region/page/source/version/overlay mismatch cases. |
| S08-T03 | Offline single-target retrieval skeleton tests; deterministic replay, scope-first filtering, budget stop. |
| S08-T04 | Static/dynamic split and stale-data tests; Shopify v0.3 limitation, chunk review needs changes, unfrozen eval, no training. |
| S08-T05 | No-upload and zero-write scans; forbidden repo artifact detection; Data-Staging read-only proof. |
| S08-T06 | Slice acceptance replay and handoff summary; no public Contract/Architecture/Decision/Workflow changes unless Human-approved separately. |

## Human Escalation Conditions

Escalate immediately before implementation continues if any task requires:

- Public Contract, Architecture, Accepted Decision, Workflow policy, or Slice 1-7
  artifact changes.
- Embedding/index construction, retrieval serving, hosted infrastructure, Milvus,
  reranker, or external-service CI.
- Live Shopify OAuth/smoke, credentials, current commerce truth, or any Shopify write.
- Copying raw PDFs, official document text, Shopify exports, staging outputs,
  embeddings, indexes, Golden Set labels, or training/fine-tuning files into the repo.
- Promoting `AI_REVIEW_NEEDS_CHANGES` chunking evidence, development-only retrieval
  metrics, or candidate Shopify v0.3 data to an approved baseline.
- Expanding beyond one Turn Target Product/Variant scope or beyond zh-CN / China
  mainland reviewed source scope.

## Recommended Next Step

Human Review should first decide whether this roadmap is an acceptable S08 planning
baseline. If accepted, establish the baseline, decide in a separate governance session
whether a workflow policy is necessary, and only then authorize S08-T01 as an offline
manifest/locator readiness task.
