# RAG Scope and Real Corpus Adapter Reconciliation Tasks

> Status: PLANNED / NON-EXECUTABLE / WAITING FOR HUMAN REVIEW
>
> These rows are not formal Slice Tasks. They cannot be selected by the Workflow
> Skill and must not be implemented until this reconciliation is accepted and a
> separate implementation scope is authorized.

| Task | Title | Status | Depends on |
|---|---|---|---|
| R01 | Identity binding, scope predicate, and regression matrix | PLANNED | Planning acceptance |
| R02 | External corpus adapter, failure/version/budget mapping | PLANNED | R01; corpus readiness |
| R03 | Preserve source-scope Evidence provenance | PLANNED | R01 |
| R04 | Integrate adapter with pilot composition without public schema change | PLANNED | R02, R03 |
| R05 | Reconcile canonical-Variant beta planning/evidence boundary | PLANNED | R01–R04 |

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
