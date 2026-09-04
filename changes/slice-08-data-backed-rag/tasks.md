# Slice 8 Tasks - Data-backed Product RAG Readiness

> Status: COMPLETED / LOCALLY INTEGRATED
>
> Human has accepted this Task table, and S08 Workflow Policy exists for fail-closed
> execution routing. S08-T01 through T06 are complete, and the completion snapshot is
> integrated into the local `main`. Post-S08 indexing, serving, Golden Set, training,
> or remote Git operations require a separate planning and approval decision.

## Ordered Tasks

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | External corpus readiness adapter | DONE | Human Review + planning baseline |
| T02 | Locator and scope binding gate | DONE | T01 |
| T03 | Offline single-target retrieval walking skeleton | DONE | T02 |
| T04 | Static/dynamic fallback and stale-data guards | DONE | T03 |
| T05 | Data boundary and no-upload verification | DONE | T04 |
| T06 | Slice readiness evidence and Human handoff | DONE | T05 |

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

S08 is closed as a data-readiness/control Slice. Human should decide whether to create
a separate post-S08 planning Slice for chunk-baseline approval, indexing/embedding
experiments, retrieval serving, or evaluation-data freeze. Until that decision and a
new approved planning baseline exist, there is no executable S08 Task.

## Task Execution Records

### S08-T01 - External Corpus Readiness Adapter

- Status: DONE
- Start commit: `eb6ba1e554e8dca049efbd004ae0027a04587657`
- Start state: detached HEAD at `eb6ba1e554e8dca049efbd004ae0027a04587657`; `git status --short --branch` reported `## HEAD (no branch)` with no dirty paths.
- Readiness: `python .agents/skills/drone-slice-workflow/scripts/inspect_state.py --authorize-task S08-T01` exited 0 and reported `selected_task=S08-T01`, `executable_task=S08-T01`, `ready_tasks=["S08-T01"]`, and no blocking reasons.
- Scope note: T02-T06 were subsequently completed in order; no remote Git, Shopify,
  embedding/index, training, or Data-Staging write operation was authorized.
- Implementation summary: added an internal read-only corpus readiness adapter and metadata-only unit fixtures; no public contract, dependency, core document, Data-Staging, embedding/index, training, Shopify, or remote Git changes.
- Real Data-Staging read check: `python -c "from backend.rag import build_corpus_readiness_report; r=build_corpus_readiness_report(); print({'stop_reason': r.stop_reason.value, 'metadata_accepted': r.metadata_accepted, 'corpus_version': r.corpus_version, 'source_count': r.source_count, 'page_locator_count': r.page_locator_count, 'rejected_count': len(r.rejected_files), 'counts': r.counts})"` exited 0 and reported `metadata_accepted=True`, `source_count=3`, `page_locator_count=261`, `rejected_count=0`, and `stop_reason=CORPUS_NOT_INDEXED`.
- Verification:
  - `python -m py_compile backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0 before final export import ordering.
  - `uv run --frozen pytest -m unit tests/unit/test_s08_t01_corpus_readiness.py -q` exited 1 during repair because missing-manifest report lacked explicit zero counts; fixed.
  - `uv run --frozen ruff check backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 1 during repair for long literal lines; fixed.
  - `uv run --frozen ruff format --check backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 1 during repair; `uv run --frozen ruff format backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0 and reformatted two files.
  - `python -m py_compile backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0.
  - `uv run --frozen pytest -m unit tests/unit/test_s08_t01_corpus_readiness.py -q` exited 0 with `8 passed`.
  - `uv run --frozen ruff check backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0.
  - `uv run --frozen ruff format --check backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0.
  - `python -c "from backend.rag import build_corpus_readiness_report; r=build_corpus_readiness_report(); print({'stop_reason': r.stop_reason.value, 'metadata_accepted': r.metadata_accepted, 'corpus_version': r.corpus_version, 'source_count': r.source_count, 'page_locator_count': r.page_locator_count, 'rejected_count': len(r.rejected_files), 'counts': r.counts})"` exited 0 first with `CORPUS_METADATA_MISMATCH` due to strict Mavic inventory/locator scope string comparison; fixed by accepting semicolon-qualified stricter inventory scope.
  - `python -c "from backend.rag import build_corpus_readiness_report; r=build_corpus_readiness_report(); print({'stop_reason': r.stop_reason.value, 'metadata_accepted': r.metadata_accepted, 'corpus_version': r.corpus_version, 'source_count': r.source_count, 'page_locator_count': r.page_locator_count, 'rejected_count': len(r.rejected_files), 'counts': r.counts})"` exited 0 with `CORPUS_NOT_INDEXED`, 3 sources, 261 page locators, and 0 rejected files.
  - `python -m py_compile backend/rag/__init__.py backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0.
  - `uv run --frozen ruff check backend/rag/__init__.py backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 1 during repair for import ordering in `backend/rag/__init__.py`; `uv run --frozen ruff check --fix backend/rag/__init__.py` exited 0 and fixed one import-order issue.
  - `uv run --frozen ruff check backend/rag/__init__.py backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0.
  - `uv run --frozen ruff format --check backend/rag/__init__.py backend/rag/corpus_readiness.py tests/unit/test_s08_t01_corpus_readiness.py` exited 0.
  - `uv run --frozen pytest -m unit tests/unit/test_s08_t01_corpus_readiness.py -q` exited 0 with `8 passed`.
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py S08-T01` exited 0 with no disallowed paths, no core artifact changes, and no dependency changes.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py S08-T01` exited 0; targeted compile, ruff, format-check, unit test, diff, core artifact, and dependency checks passed.
  - `git diff --check` exited 0.
  - `git status --short --untracked-files=all` exited 0 and showed only `backend/rag/__init__.py`, `backend/rag/corpus_readiness.py`, `changes/slice-08-data-backed-rag/tasks.md`, and `tests/unit/test_s08_t01_corpus_readiness.py`.
- Snapshot: not created; S08-T01 was completed as working-tree changes only, with no commit and no push.

### S08-T02 - Locator and Scope Binding Gate

- Status: DONE
- Start commit: `08f324e1f99cf767c8f76ed5afa8c5c9769e5643`
- Start state: branch `codex/s08-implementation` at `08f324e1f99cf767c8f76ed5afa8c5c9769e5643`; `git status --short --branch` reported `## codex/s08-implementation` with no dirty paths.
- Readiness: `python .agents/skills/drone-slice-workflow/scripts/inspect_state.py --authorize-task S08-T02` exited 0 and reported `selected_task=S08-T02`, `executable_task=S08-T02`, `ready_tasks=["S08-T02"]`, and no blocking reasons.
- Scope note: used existing internal `ObjectScope` / `SourceLocator` semantics without modifying `backend/common/contracts.py`; no public contract, Architecture, dependency, Shopify, embedding/index, training, Data-Staging write, or remote Git change was made.
- Implementation summary: added an internal metadata-only locator binding gate with exact mismatch reasons for product, variant, language, region, source_ref, source_id, version, checksum, page, locator, and Mavic 3/Cine overlay exclusion; exported the internal API from `backend.rag`; added focused unit and contract tests using small metadata-only fixtures.
- Verification:
  - `python -m py_compile backend/rag/locator_binding.py tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py` exited 0.
  - `uv run --frozen pytest -m 'unit or contract' tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py -q` exited 0 with `16 passed`.
  - `uv run --frozen ruff check backend/rag/__init__.py backend/rag/locator_binding.py tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py` exited 1 during repair for two quoted type annotations; fixed. This command created a local `.venv`; removed `/private/tmp/consumer-drone-s08-implementation/.venv`.
  - `uv run --frozen ruff format --check backend/rag/__init__.py backend/rag/locator_binding.py tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py` exited 1 during repair; `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format backend/rag/__init__.py backend/rag/locator_binding.py tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py` exited 0 and reformatted one file.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m py_compile backend/rag/locator_binding.py tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m 'unit or contract' tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py -q` exited 0 with `16 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/locator_binding.py tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache backend/rag/__init__.py backend/rag/locator_binding.py tests/unit/test_s08_t02_locator_binding.py tests/contract/test_s08_t02_locator_binding_contract.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/check_scope.py S08-T02` exited 0 with no disallowed paths, no core artifact changes, and no dependency changes.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/verify_task.py S08-T02` exited 0; targeted compile, ruff, format-check, unit/contract tests, diff, core artifact, and dependency checks passed. This helper used `uv run` internally and created a local `.venv`; removed `/private/tmp/consumer-drone-s08-implementation/.venv`.
- Snapshot: not created; S08-T02 is HIGH risk with Human-authorized implementation, and no MEDIUM checkpoint applies.

### S08-T03 - Offline Single-target Retrieval Walking Skeleton

- Status: DONE
- Start commit: `8d574443ddf89f7a28570238c4395912964fc571`
- Start state: branch `codex/s08-implementation` at `8d574443ddf89f7a28570238c4395912964fc571`; `git status --short --branch --untracked-files=all` reported `## codex/s08-implementation` with no dirty paths.
- Readiness: `python .agents/skills/drone-slice-workflow/scripts/inspect_state.py --authorize-task S08-T03` exited 0 and reported `selected_task=S08-T03`, `executable_task=S08-T03`, `ready_tasks=["S08-T03"]`, and no blocking reasons.
- Scope note: implemented an offline metadata-only walking skeleton; no embeddings, indexes, retrieval service, reranker, live model generation, open-web access, public contract change, dependency change, Shopify access, training, Data-Staging write, or remote Git operation was made.
- Implementation summary: added an internal `OfflineMetadataLocatorRetriever` that reuses `RetrievalRequest` and `RetrievalStrategy`, filters candidates through the S08 locator binding gate before scoring, returns bounded metadata locator candidates, and fails closed with `NO_SCOPED_MATCH`, `CORPUS_NOT_INDEXED`, or `SCOPED_CANDIDATE_LIMIT`.
- Verification:
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m py_compile backend/rag/offline_retrieval.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m integration tests/integration/test_s08_t03_offline_metadata_retrieval.py -q` exited 1 during repair because the cross-product rejection test expected 3 filtered records while the scope/score gate correctly filtered all 4 non-returned records; fixed.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/offline_retrieval.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 1 during repair for one long line; fixed.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache backend/rag/__init__.py backend/rag/offline_retrieval.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 1 during repair; `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --no-cache backend/rag/__init__.py backend/rag/offline_retrieval.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 0 and reformatted one file.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m py_compile backend/rag/offline_retrieval.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m integration tests/integration/test_s08_t03_offline_metadata_retrieval.py -q` exited 0 with `7 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/offline_retrieval.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache backend/rag/__init__.py backend/rag/offline_retrieval.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/check_scope.py S08-T03` exited 0 with no disallowed paths, no core artifact changes, and no dependency changes.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/verify_task.py S08-T03` exited 0; targeted compile, ruff, format-check, integration test, diff, core artifact, and dependency checks passed. This helper used `uv run` internally and created a local `.venv`; removed `/private/tmp/consumer-drone-s08-implementation/.venv`, `.pytest_cache`, and `.ruff_cache`.
- Snapshot: `856237d66c7032bdf042f3d06c1c104e1ec9754d`
- Review/checkpoint: independent review evidence `/private/tmp/consumer-drone-s08-t03-review-evidence.json` reported `AI_REVIEW_PASS`; `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/verify_commit_readiness.py S08-T03 --checkpoint --base-head 8d574443ddf89f7a28570238c4395912964fc571 --snapshot-head 856237d66c7032bdf042f3d06c1c104e1ec9754d --reviewed-digest 324dfbf4ee13d9eefa420787bf38bfa50744ebbf66dd219bac4f21d09bf4b19a --risk-tier MEDIUM --review-evidence /private/tmp/consumer-drone-s08-t03-review-evidence.json` exited 0 with `AUTO_ADVANCE_ELIGIBLE`, `digest_matches=true`, and `auto_advance=true`.

### S08-T04 - Static/Dynamic Fallback and Stale-data Guards

- Status: DONE
- Start commit: `856237d66c7032bdf042f3d06c1c104e1ec9754d`
- Start state: branch `codex/s08-implementation` at `856237d66c7032bdf042f3d06c1c104e1ec9754d`; `git status --short --branch --untracked-files=all` reported `## codex/s08-implementation` with no dirty paths.
- Readiness: `python .agents/skills/drone-slice-workflow/scripts/inspect_state.py --authorize-task S08-T04` exited 0 and reported `selected_task=S08-T04`, `executable_task=S08-T04`, `ready_tasks=["S08-T04"]`, and no blocking reasons.
- Scope note: implemented internal static/dynamic and stale-data guards under `backend/rag`; no live Shopify/OAuth, public contract, Architecture, dependency, embedding/index, training, Data-Staging write, or remote Git change was made.
- Implementation summary: added `StaticRagPreflightRequest` / `StaticRagPreflightReport` and exact internal stop reasons for `DYNAMIC_FACT_REQUIRED`, `CORPUS_VERSION_MISMATCH`, `CHUNK_BASELINE_MANIFEST_MISSING`, `CHUNK_BASELINE_NEEDS_CHANGES`, `SHOPIFY_CANDIDATE_LIMITATION`, `GOLDEN_SET_NOT_FROZEN`, and `TRAINING_NOT_AUTHORIZED`; wired dynamic-commerce question detection into the offline metadata retriever before locator scoring.
- Verification:
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m py_compile backend/rag/static_dynamic_guards.py backend/rag/offline_retrieval.py tests/contract/test_s08_t04_static_dynamic_guards.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m 'contract or integration' tests/contract/test_s08_t04_static_dynamic_guards.py tests/integration/test_s08_t03_offline_metadata_retrieval.py -q` exited 0 with `15 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/offline_retrieval.py backend/rag/static_dynamic_guards.py tests/contract/test_s08_t04_static_dynamic_guards.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache backend/rag/__init__.py backend/rag/offline_retrieval.py backend/rag/static_dynamic_guards.py tests/contract/test_s08_t04_static_dynamic_guards.py tests/integration/test_s08_t03_offline_metadata_retrieval.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/check_scope.py S08-T04` exited 0 with no disallowed paths, no core artifact changes, and no dependency changes.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/verify_task.py S08-T04` exited 0; targeted compile, ruff, format-check, contract test, diff, core artifact, and dependency checks passed with `8 passed`. This helper used `uv run` internally and created local caches; removed `/private/tmp/consumer-drone-s08-implementation/.venv`, `.pytest_cache`, and `.ruff_cache`.
- Snapshot: not created; S08-T04 is HIGH risk with Human-authorized implementation, and no MEDIUM checkpoint applies.

### S08-T05 - Data Boundary and No-upload Verification

- Status: DONE
- Start commit: `329ce884392965284c98c91345ea6535a2e81f21`
- Start state: branch `codex/s08-implementation` at `329ce884392965284c98c91345ea6535a2e81f21`; `git status --short --branch --untracked-files=all` reported `## codex/s08-implementation` with no dirty paths.
- Readiness: `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/inspect_state.py --authorize-task S08-T05` exited 0 and reported `selected_task=S08-T05`, `executable_task=S08-T05`, `ready_tasks=["S08-T05"]`, and no blocking reasons.
- Scope note: added repository-local no-upload and zero-write verification helpers only; no raw PDFs, official document text, Shopify exports, staging outputs, embeddings, indexes, secrets, Golden Set labels, training files, dependency changes, public contract changes, Shopify writes, Data-Staging writes, or remote Git operations were introduced.
- Implementation summary: added an internal `DataBoundaryReport` scanner and `scripts/check_s08_data_boundary.py` CLI that checks changed repo paths/content and actual command evidence for forbidden S08 data artifacts, Data-Staging write commands, remote Git commands, and Shopify write commands; tests use only synthetic bytes and metadata-style paths.
- Verification:
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m py_compile backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m unit tests/unit/test_s08_t05_data_boundary.py -q` exited 5 during repair because the new test file lacked the `unit` marker; fixed.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m unit tests/unit/test_s08_t05_data_boundary.py -q` exited 0 with `8 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py` exited 1 during repair for subprocess `capture_output` and line-length issues; fixed.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache backend/rag/__init__.py backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py` exited 1 during repair; `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --no-cache tests/unit/test_s08_t05_data_boundary.py` exited 0 and reformatted one file, then `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --no-cache backend/rag/data_boundary.py tests/unit/test_s08_t05_data_boundary.py` exited 0 and reformatted two files.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python scripts/check_s08_data_boundary.py --command "git status --short --branch --untracked-files=all" --command "PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m unit tests/unit/test_s08_t05_data_boundary.py -q"` exited 1 during repair because the standalone script needed repo-root import bootstrapping; fixed.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python scripts/check_s08_data_boundary.py --command "git status --short --branch --untracked-files=all" --command "PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m unit tests/unit/test_s08_t05_data_boundary.py -q" --command "PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py"` exited 1 during repair because scanner/test detection signatures appeared literally in scanner/test source; fixed by splitting literals while preserving runtime checks.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m py_compile backend/rag/__init__.py backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m unit tests/unit/test_s08_t05_data_boundary.py -q` exited 0 with `8 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache backend/rag/__init__.py backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python scripts/check_s08_data_boundary.py --command "git status --short --branch --untracked-files=all" --command "PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m unit tests/unit/test_s08_t05_data_boundary.py -q" --command "PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/data_boundary.py scripts/check_s08_data_boundary.py tests/unit/test_s08_t05_data_boundary.py" --command "PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/verify_task.py S08-T05"` exited 0 with `accepted=true`, five checked paths, four checked commands, and no violations.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/check_scope.py S08-T05` exited 0 with no disallowed paths, no core artifact changes, and no dependency changes.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/verify_task.py S08-T05` exited 0; targeted compile, ruff, format-check, unit test, diff, core artifact, and dependency checks passed with `8 passed`. This helper used `uv run` internally and created local caches; removed `/private/tmp/consumer-drone-s08-implementation/.venv`, `.pytest_cache`, and `.ruff_cache`.
- Snapshot: `983aebf27ec859ae2f742c647d93a025d931f32c`
- Review/checkpoint: Human explicitly approved skipping the S08-T05 independent review checkpoint based on snapshot `983aebf27ec859ae2f742c647d93a025d931f32c` and recorded targeted verification; no AI Human-approval claim is made.
- Evidence digest: `052aa17b95c8964ccf3cf2607c45f729230d8bdbee769bec5e3c933db090a2df`

### S08-T06 - Slice Readiness Evidence and Human Handoff

- Status: DONE
- Start commit: `983aebf27ec859ae2f742c647d93a025d931f32c`
- Start state: branch `codex/s08-implementation` at `983aebf27ec859ae2f742c647d93a025d931f32c`; `git status --short --branch --untracked-files=all` reported `## codex/s08-implementation`, with existing T06 draft changes in `backend/rag/__init__.py`, `backend/rag/s08_readiness.py`, and `tests/e2e/test_s08_t06_completion_matrix.py` treated as in-scope per current Human instruction.
- Readiness: `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/inspect_state.py --authorize-task S08-T06` exited 1 because the same worktree already contained in-scope T06 draft files, but it reported `selected_task=S08-T06`, `ready_tasks=["S08-T06"]`, T05 dependency satisfied, implementation gate satisfied, and `CURRENT_WORKTREE_DIRTY` as the only execution blocker.
- Scope note: completed Slice-readiness evidence and Human handoff only; no public Contract, Architecture, Accepted Decision, dependency, workflow policy, raw PDF, official text, Shopify export, staging output, embedding, index, Golden Set, training/fine-tuning, Shopify write, Data-Staging write, remote Git, push, merge, S09, or production RAG serving change was made.
- Implementation summary: added an internal `S08ReadinessHandoff` model and completion matrix evidence checks that keep the corpus explicitly `CORPUS_NOT_INDEXED`, require the S08 matrix rows to pass, require no-upload/data-boundary acceptance, and preserve deferred post-S08 decisions for chunk baseline approval, embeddings, indexes, production serving, Golden Set freeze, training/fine-tuning, and live Shopify truth.
- Verification:
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m py_compile backend/rag/__init__.py backend/rag/s08_readiness.py tests/e2e/test_s08_t06_completion_matrix.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m e2e tests/e2e/test_s08_t06_completion_matrix.py -q` exited 0 with `3 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache backend/rag/__init__.py backend/rag/s08_readiness.py tests/e2e/test_s08_t06_completion_matrix.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache backend/rag/__init__.py backend/rag/s08_readiness.py tests/e2e/test_s08_t06_completion_matrix.py` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/check_scope.py S08-T06` exited 0 with no disallowed paths, no core artifact changes, and no dependency changes.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python scripts/check_s08_data_boundary.py --command "git status --short --branch --untracked-files=all" --command "PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m e2e tests/e2e/test_s08_t06_completion_matrix.py -q"` exited 0 with `accepted=true`, four checked paths, two checked commands, and no violations.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff check --no-cache .` exited 0.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/ruff format --check --no-cache .` exited 0 with `152 files already formatted`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python -m pytest -p no:cacheprovider -m 'unit or contract or integration or e2e' -q` exited 0 with `605 passed`.
  - `PYTHONDONTWRITEBYTECODE=1 /Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent/.venv/bin/python .agents/skills/drone-slice-workflow/scripts/verify_task.py S08-T06` exited 0; Slice-completion compile, `uv lock --check`, full ruff, full format-check, full pytest, diff, core artifact, and dependency checks passed with `605 passed`. This helper used `uv run` internally and created local caches; removed `/private/tmp/consumer-drone-s08-implementation/.venv`, `.pytest_cache`, and `.ruff_cache` before snapshot.
- Snapshot: `77d7ced805216c612d9b06bf5312c83ba9e7cdde` (completion snapshot; locally
  fast-forward integrated to `main`); final independent Slice Review was explicitly
  waived by Human approval. S08-T06 is complete and no S08 Task remains executable.
