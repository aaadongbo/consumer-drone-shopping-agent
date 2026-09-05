# RAG Scope and Real Corpus Adapter Reconciliation Tasks

> Status: FORMAL IMPLEMENTATION SCOPE / RAG-R04 DONE
>
> The RAG policy is present in the integrated Workflow baseline and the current
> context authorizes R01–R05 in order. Only the current Task may be active; later
> rows remain non-executable until their dependencies and task gate are met.

| Task | Title | Status | Depends on |
|---|---|---|---|
| R01 | Identity binding, scope predicate, and regression matrix | DONE | Planning baseline; current-context RAG authorization |
| R02 | External corpus adapter, failure/version/budget mapping | DONE | R01; corpus readiness; current-context RAG authorization |
| R03 | Preserve source-scope Evidence provenance | DONE | R01; policy activation |
| R04 | Integrate adapter with pilot composition without public schema change | DONE | R02, R03; policy activation |
| R05 | Reconcile canonical-Variant beta planning/evidence boundary | NOT_STARTED | R01–R04; policy activation |

## Formalization boundary

- This table is the implementation scope and dependency order for the reconciliation.
- No Workflow policy, allowlist, risk tier, or verification profile is activated by
  this file alone.
- The scope is separate from S11; it must not change S11 `tasks.md` or make S11-T04
  executable.
- The integrated RAG policy defines the allowed paths, risk tiers, and targeted
  gates; a current-context authorization is still required before a row changes
  from `NOT_STARTED` to `IN_PROGRESS`.

## R01 — Identity binding, scope predicate, and regression matrix

- **Goal**: bind external corpus Product/Variant keys exactly to approved Shopify
  identities and allow Product-shared records for a confirmed Variant while rejecting
  foreign Variant records.
- **Scope**: internal `CorpusScopeBinding`, checksum-bound manifest mapping,
  `controlled_retrieval` predicate, and direct regression matrix.
- **Acceptance**: `(corpus_store_id, corpus_product_key, optional corpus_variant_key,
  manifest_sha256)` resolves only to the approved canonical ObjectScope; Product
  requests match only `variant_id = null`; Variant requests match same-Product shared
  records plus the exact requested Variant records.
- **Acceptance**: shared static record is retrievable for a Variant; Variant A/B
  records cannot cross; Product-only cannot read Variant-specific facts; no default
  Variant selection occurs; name/slug/fuzzy and cross-Store fallback is rejected.
- **Data model**: Product-level corpus records are stored once as shared knowledge;
  Variant overlays carry bundle/accessory/controller/battery differences, and a
  Variant document is admitted only when an official supplemental procedure or
  materially different rule exists.
- **Verification**: targeted unit/contract/integration checks only.
- **Out of scope**: dynamic Shopify facts, Product/Variant selection, comparison,
  recommendation, public Contract.

## R02 — External corpus adapter, failure/version/budget mapping

- **Goal**: adapt validated ephemeral reader output to the existing retriever input
  shape without copying protected source data.
- **Data flow**: `RetrievalRequest → CorpusScopeBinding →
  ControlledRetrievalRequest → ExternalCorpusReader → ExternalCorpusReadResult →
  RetrievalResult → Evidence Gate`.
- **Contract**: internal typed adapter preserving scope, locator, checksum, manifest
  identity, per-source version, provenance, `k`, token/deadline budgets,
  `filtered_out_count`, and a typed stop reason; no public wire change.
- **Version gate**: `RetrievalResult.index_version` is the manifest identity;
  `chunk.version` is the source version. Evidence validation checks both source
  version consistency and manifest identity equality.
- **Acceptance**: invalid manifest/checksum/scope, undeclared source version, `k`,
  token, or deadline budget failure stops before Evidence; accepted records remain
  ephemeral and metadata-bound; the reader is not invoked twice for one request.
- **Budget ownership**: `BoundedProductRagLoop` alone owns Action Round/tool-call
  counters; the adapter reports consumption and stop reasons but cannot reset or
  exceed those counters.
- **Out of scope**: index, embeddings, vector store, reranker, model, database,
  network access, or raw corpus persistence.

## R03 — Preserve source-scope Evidence provenance

- **Goal**: ensure Product-shared and Variant-specific corpus records retain their
  original scope through Product RAG Evidence construction.
- **Acceptance**: Product-shared evidence keeps `variant_id = null`; Variant-specific
  evidence keeps the exact source Variant ID; Turn Target scope never overwrites
  source provenance; dynamic Shopify Evidence remains exact-Variant scoped.
- **Verification**: targeted Evidence unit/contract/integration tests and no public
  Contract change.

## R04 — Pilot composition integration

- **Goal**: make the controlled retrieval composition capable of receiving the real
  corpus adapter through injection.
- **Acceptance**: existing synthetic tests remain valid; approved external corpus
  adapter can be injected in a local read-only pilot; static/dynamic source
  separation and Evidence gates remain unchanged.
- **Escalation**: any public Contract, dependency, or external-service change stops.

## R05 — Canonical-Variant planning/evidence boundary

- **Goal**: record the current S10/S11 beta limitation precisely.
- **Acceptance**: one canonical Variant per Product is explicit; no claim of
  multi-Variant bundle isolation is made; real secondary Variants require a future
  approved scope and acceptance matrix.
- **Artifacts**: update only this reconciliation's `plan.md`/`tasks.md` to record the
  canonical-Variant limitation. Do not modify S10 evidence, S11 `tasks.md`, public
  Contracts, or runtime code in R05; any S11 synchronization is a later S11 planning
  reconciliation.
- **Verification**: planning/evidence reconciliation only.

## RAG-R01 Execution Record

- **Status**: `DONE`
- **Start commit**: `0603339a52daeb29ce1422986550e038c39bbb1e`
- **Start worktree**: clean; no staged or untracked files before implementation.
- **Authorization**: current-context authorization for the formal RAG-R01 through
  RAG-R05 scope; RAG-R01 is the selected first Task and is HIGH within that
  authorization.
- **Boundary**: internal corpus identity binding, canonical ObjectScope mapping,
  Product-shared/Variant-specific retrieval predicate, and regression tests only.
  No public Contract, external access, source corpus content, persistence,
  dependency, Workflow change, or S11 Task change.
- **Implementation**: Added immutable `CorpusScopeBinding`, exact-key
  `CorpusScopeBindingRegistry`, typed binding results/rejections, and
  `bind_corpus_scope`/`resolve_corpus_scope`. Matching requires exact corpus
  store/product/variant keys and the exact manifest checksum; unknown names,
  slugs, aliases, and fuzzy candidates are not consulted. Controlled retrieval
  now admits Product-shared records for an exact Variant request while keeping
  Product-only requests shared-only and rejecting foreign Variant records.
- **Targeted verification**:
  - `UV_CACHE_DIR=/private/tmp/consumer-drone-uv-cache uv run ruff check ...`
    first exited `1` because the sandbox could not download locked packages;
    after the approved local dependency preparation,
    `.venv/bin/ruff check backend/rag/scope_binding.py
    backend/rag/controlled_retrieval.py backend/rag/__init__.py
    tests/unit/test_rag_r01_scope_binding.py
    tests/integration/test_rag_r01_scope_matrix.py` exited `0`.
  - `.venv/bin/ruff format --check backend/rag/scope_binding.py
    backend/rag/controlled_retrieval.py backend/rag/__init__.py
    tests/unit/test_rag_r01_scope_binding.py
    tests/integration/test_rag_r01_scope_matrix.py` exited `0`.
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -m 'unit or integration'
    tests/unit/test_rag_r01_scope_binding.py
    tests/integration/test_rag_r01_scope_matrix.py
    tests/integration/test_s09_t02_t03_controlled_retrieval.py -q` exited `0`
    with `17 passed in 0.16s`.
  - `python .agents/skills/drone-slice-workflow/scripts/check_scope.py RAG-R01`
    exited `0`; all changed paths matched the R01 allowlist and no core,
    dependency, forbidden-data, or semantic violations were reported.
  - `python .agents/skills/drone-slice-workflow/scripts/verify_task.py RAG-R01`
    exited `0`; syntax, changed-file lint/format, targeted tests, diff, core
    artifact, and dependency gates passed (`12 passed in 0.16s` for its selected
    R01 tests).
  - `git diff --check` exited `0`.
- **Repair notes**: the first test collection attempt exited `2` because pytest
  reserves the parameter name `request`; the next run exited `1` with three
  fixture assertions because the matrix accidentally queried records assigned
  to the requested foreign scope. Both were corrected within R01 and the final
  targeted run passed.
- **Known limits**: this Task does not validate external corpus reads, source
  versions, adapter budgets, Evidence provenance construction, pilot injection,
  or canonical-Variant planning; those remain R02–R05 scope.

## RAG-R02 Execution Record

- **Status**: `DONE`
- **Start commit**: `d30644a482a43452c18db883b30eb8ac2b59797e`
- **Start worktree**: clean after the RAG-R01 immutable snapshot; no staged or
  untracked files before implementation.
- **Authorization**: current-context authorization for the formal RAG-R01 through
  RAG-R05 scope; RAG-R01 completed with `AI_REVIEW_PASS`, and RAG-R02 is the
  dependency-ready MEDIUM Task.
- **Boundary**: internal ExternalCorpusReader adapter, manifest identity/source
  version separation, failure and budget metadata, and targeted tests only. No
  public Contract, external/network access, persistence, dependency, Workflow
  change, Evidence provenance rewrite, or S11 Task change.
- **Implementation**: Added `CorpusManifestIdentity` carrying internal
  `schema_version`, `corpus_version`, and `manifest_sha256`, with a deterministic
  `RetrievalResult.index_version` representation. External reads now annotate
  ephemeral chunks with manifest identity while retaining each chunk's source
  version, language, region, and record provenance. Added a single-pass adapter
  from `RetrievalRequest` through exact `CorpusScopeBinding` to
  `ControlledRetrievalRequest`, then from `ExternalCorpusReadResult` to the
  existing `RetrievalResult` shape. Adapter output preserves configured and
  consumed budgets, source versions, and `filtered_out_count`; returned manifests,
  candidates, scopes, locators, and text checksums are cross-validated before
  Evidence. Empty, reader failure, deadline, checksum, version, scope, and budget
  mismatch paths stop before Evidence.
- **Targeted verification**:
  - `.venv/bin/ruff check backend/rag/controlled_retrieval.py
    backend/rag/external_corpus_reader.py backend/rag/manifest_identity.py
    backend/rag/external_corpus_adapter.py backend/rag/__init__.py
    tests/unit/test_rag_r02_external_corpus_adapter.py
    tests/unit/test_s10_t02_external_corpus_reader.py` exited `0` with
    `All checks passed!`.
  - `.venv/bin/ruff format --check backend/rag/controlled_retrieval.py
    backend/rag/external_corpus_reader.py backend/rag/manifest_identity.py
    backend/rag/external_corpus_adapter.py backend/rag/__init__.py
    tests/unit/test_rag_r02_external_corpus_adapter.py
    tests/unit/test_s10_t02_external_corpus_reader.py` exited `0` with
    `7 files already formatted`.
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -m
    'unit or contract or integration' tests/unit/test_rag_r02_external_corpus_adapter.py
    tests/unit/test_s10_t02_external_corpus_reader.py
    tests/integration/test_s10_t02_external_corpus_reader_live.py
    tests/integration/test_rag_r01_scope_matrix.py
    tests/unit/test_rag_r01_scope_binding.py
    tests/integration/test_s09_t02_t03_controlled_retrieval.py -q` exited `0`
    with `38 passed in 0.17s`.
  - `git diff --check` exited `0`.
- **Repair notes**: the first lint pass exited `1` after a retry had inserted
  duplicate adapter exports into `backend/rag/__init__.py`; the duplicate block
  was removed. Independent review of snapshot
  `47fe1974fd49838bdc893814fe976d1391a87fcd` with digest
  `13c6c55d4cd11e9f73729513e483e2f6c8e95d1aab3e47b0a8ee52e07da867ce` returned
  `AI_REVIEW_NEEDS_CHANGES` for missing returned-manifest checksum binding,
  incomplete returned-scope/candidate validation, unreported/exceeded action
  budget, missing language/region provenance, uncaught loader failures, and
  duplicate exports. The fresh implementation repairs these findings and adds
  regression coverage. Independent review of the repaired snapshot
  `b9404446995b7508ff92091c5a604b10f7f3ac95` with digest
  `eaac54ba45b3d42c19c10262136bd2dae972f5d0b3e1aaf8775bd5306a5a527c` then
  returned `AI_REVIEW_NEEDS_CHANGES` for missing caller-request binding and
  duplicate candidate/chunk rejection. The second repair requires the caller's
  exact controlled request and rejects duplicate IDs with regression coverage;
  a fresh immutable snapshot and independent review are required before
  checkpoint evaluation.
- **Known limits**: the existing Evidence Gate still owns source-scope Evidence
  provenance and its manifest/source-version acceptance semantics; those are
  R03 scope. This Task does not integrate pilot composition or change ActionPlan
  ownership in `BoundedProductRagLoop`.

## RAG-R03 Execution Record

- **Status**: `DONE`
- **Start commit**: `87356360ab279246305299f444dbfacabc628070`
- **Start worktree**: clean after the RAG-R02 immutable snapshot and MEDIUM
  checkpoint returned `AUTO_ADVANCE_ELIGIBLE`; no staged or untracked files before
  implementation.
- **Authorization**: current-context authorization for the formal RAG-R01 through
  RAG-R05 scope; RAG-R03 is the dependency-ready HIGH Task.
- **Boundary**: internal Evidence Gate version/provenance validation and targeted
  Evidence tests only. Product-shared Evidence retains `variant_id = null`,
  Variant-specific Evidence retains its source Variant ID, and no target scope is
  copied into a source chunk. No public Contract, external/network access,
  persistence, dependency, Workflow change, pilot composition, or S11 Task change.
- **Implementation**: Evidence Gate now treats an external chunk's
  `metadata["manifest_identity"]` as the manifest/index identity and compares it
  with `RetrievalResult.index_version`, while independently requiring the chunk
  locator to retain the source version and source ID. Legacy internal document
  chunks without manifest metadata keep the existing document-version check.
  Added Product-shared, exact Variant, cross-Variant/cross-Product,
  Product-only, and manifest-identity mismatch regression coverage.
- **Targeted verification**:
  - `.venv/bin/ruff check backend/evidence/rag_quality.py
    tests/unit/test_rag_r03_source_scope_evidence.py` exited `0` with
    `All checks passed!`.
  - `.venv/bin/ruff format --check backend/evidence/rag_quality.py
    tests/unit/test_rag_r03_source_scope_evidence.py` exited `0` with
    `2 files already formatted`.
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -m
    'unit or contract or integration'
    tests/unit/test_rag_r03_source_scope_evidence.py
    tests/contract/test_s05_t04_evidence_gate_contract.py
    tests/integration/test_s05_t04_evidence_quality.py
    tests/integration/test_s05_t05_rag_loop.py
    tests/unit/test_rag_r02_external_corpus_adapter.py
    tests/integration/test_s10_t02_external_corpus_reader_live.py -q` exited
    `0` with `31 passed in 0.26s`.
  - `git diff --check` exited `0`.
- **Known limits**: pilot composition injection remains R04 scope. This HIGH Task
  has not been integrated into a protected branch or pushed; a fresh independent
  semantic review is required for the immutable snapshot.

## RAG-R04 Execution Record

- **Status**: `DONE`
- **Start commit**: `b9f31c6fdc7c8b8f6e8b3aad8c93ff9fb27cb6cc`
- **Start worktree**: clean after the RAG-R03 immutable snapshot and independent
  `AI_REVIEW_PASS`; no staged or untracked files before implementation.
- **Authorization**: current-context authorization for the formal RAG-R01 through
  RAG-R05 scope; RAG-R04 is the dependency-ready MEDIUM Task.
- **Boundary**: internal external-corpus retriever injection into the existing
  pilot composition, source-scope Evidence preservation, and targeted pilot tests.
  No public Contract, external/network access, persistence, dependency, Workflow,
  or S11 Task change.
- **Implementation**: Added `ExternalCorpusProductRetriever`, which resolves an
  exact canonical ObjectScope from an immutable binding registry, calls the
  existing single-pass external adapter, and maps typed read failures to an empty
  internal `RetrievalResult` so the existing bounded loop and Evidence Gate remain
  the owners of budgets and acceptance. Pilot composition continues to receive
  the retriever through its existing injection port. Product RAG Evidence now
  copies store/product/variant provenance from the accepted source chunk. The API
  factory import is deferred until composition construction to remove the
  pre-existing application/runtime package initialization cycle.
- **Targeted verification**:
  - `.venv/bin/ruff check backend/rag/external_corpus_adapter.py
    backend/rag/__init__.py backend/application/product_rag.py
    backend/application/pilot_composition.py
    tests/integration/test_rag_r04_pilot_composition.py` exited `0` with
    `All checks passed!`.
  - `.venv/bin/ruff format --check` on the same five changed Python files exited
    `0` with `5 files already formatted`.
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -m
    'unit or contract or integration'` over the R04 pilot, existing S10 pilot,
    Product RAG loop, RAG-R02 adapter, and RAG-R03 provenance tests exited `0`
    with `37 passed in 0.37s`.
  - `git diff --check` exited `0`.
- **Repair notes**: the first lint attempt exited `1` for import ordering and
  line length; Ruff formatting and import fixing corrected it. The first test
  collection exited `2` on the existing application/runtime import cycle; the
  pilot API factory import was deferred inside the composition builder and the
  final targeted collection passed.
- **Known limits**: this Task proves pilot injection with an injected read-only
  external reader; the approved source-region smoke remains R02/S10-T02 scope.
  This MEDIUM Task has not been integrated into a protected branch or pushed; a
  fresh immutable snapshot, independent review, and checkpoint evaluation are
  required.
