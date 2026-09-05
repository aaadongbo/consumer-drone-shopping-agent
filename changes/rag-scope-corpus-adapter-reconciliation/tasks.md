# RAG Scope and Real Corpus Adapter Reconciliation Tasks

> Status: FORMAL IMPLEMENTATION SCOPE / RAG-R01 IN PROGRESS
>
> The RAG policy is present in the integrated Workflow baseline and the current
> context authorizes R01–R05 in order. Only the current Task may be active; later
> rows remain non-executable until their dependencies and task gate are met.

| Task | Title | Status | Depends on |
|---|---|---|---|
| R01 | Identity binding, scope predicate, and regression matrix | DONE | Planning baseline; current-context RAG authorization |
| R02 | External corpus adapter, failure/version/budget mapping | NOT_STARTED | R01; corpus readiness; policy activation |
| R03 | Preserve source-scope Evidence provenance | NOT_STARTED | R01; policy activation |
| R04 | Integrate adapter with pilot composition without public schema change | NOT_STARTED | R02, R03; policy activation |
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
