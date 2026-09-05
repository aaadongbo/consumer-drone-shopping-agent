# RAG Scope and Real Corpus Adapter Planning Reconciliation

> Status: DRAFT / NON-EXECUTABLE / HUMAN REVIEW REQUIRED
>
> This is a planning reconciliation only. It does not activate a Slice, authorize
> implementation, change the public Contract, access Shopify, read external corpus
> content, or modify Workflow policy.

## 1. Purpose

Reconcile the existing S09/S10 retrieval design with the intended knowledge model:

> Product-shared knowledge may be inherited by a confirmed Variant; Variant-specific
> knowledge and dynamic commerce facts must remain exact-Variant scoped.

The reconciliation addresses two bounded gaps:

1. `controlled_retrieval.py` currently requires an exact `variant_id` match and can
   therefore exclude Product-shared records (`variant_id = null`) for a Variant turn.
2. `ExternalCorpusReader` validates and loads approved source regions, but the S10
   composition boundary does not yet expose a stable adapter into the existing
   `ProductRagRetriever` input path.
3. The current Product RAG evidence builder must preserve the source record's scope;
   a Product-shared record must not acquire the Turn Target's `variant_id` merely
   because the question was asked from a Variant page.

## 2. Current facts

- Public `ProductRecord`, `VariantRecord`, `Evidence`, and commerce contracts already
  distinguish Product-shared and Variant-specific data.
- Shopify dynamic price, inventory, and availability are already bound to the exact
  requested Variant.
- S09 controlled retrieval is single-Product and scope-first; it is not a
  multi-product retrieval system.
- S10 has three approved Products with one canonical stable Variant ID each. This
  proves identity binding but does not prove isolation between multiple real variants
  of one Product.
- S10's real corpus reader and pilot composition were validated separately; the
  composition tests primarily use an injected synthetic retriever.

## 3. Proposed scope semantics

The internal scope predicate should be:

```text
Product request (variant_id = null)
  -> Product-shared records only (record.variant_id = null)

Confirmed Variant request
  -> Product-shared records for the same store/product
  -> Variant-specific records for the same store/product/variant
  -> reject every other Variant record
```

The rule applies only to static corpus metadata. It never permits:

- one Variant's packaging, battery, price, inventory, availability, or other fact to
  be promoted to Product scope;
- a Product-only request to answer a Variant-specific or dynamic commerce question;
- cross-Product or cross-Store fallback;
- default selection of a Variant;
- static corpus evidence to impersonate current Shopify commerce state.

Internal metadata continues to use `variant_id = null` for Product-shared records and
the exact stable ID for Variant-specific records. No public wire field is added.

## 4. Corpus identity and version binding

The adapter must introduce an internal, typed `CorpusScopeBinding` before retrieval:

```text
(corpus_store_id, corpus_product_key, optional corpus_variant_key,
 manifest_sha256) -> canonical ObjectScope
manifest_sha256 + manifest_version -> admitted corpus identity
```

Bindings are checksum-bound to the admitted manifest and approved Product/Variant
metadata, and include the corpus-side Store identity. Display names, slugs, aliases,
and fuzzy similarity are never sufficient to resolve an identity. Missing, duplicate,
foreign, cross-Store, or changed mappings stop with a typed internal reason before
retrieval scoring.

The manifest version and each source's `source_version` must both be retained:

- `manifest_version` identifies the admitted corpus manifest used by the run;
- `source_version` identifies the exact source revision for each candidate;
- the adapter verifies that every candidate source version is declared by the manifest
  and that its checksum/locator belongs to that manifest;
- an undeclared or mismatched source version stops before Evidence construction.

The internal version model deliberately separates two existing fields:

- `RetrievalResult.index_version` is the admitted manifest identity (manifest version
  plus checksum), not an individual source revision;
- `chunk.version` remains the source version for that chunk.

The Evidence Gate verifies both that each chunk/locator carries the declared source
version and that its metadata manifest identity equals `RetrievalResult.index_version`.
This is an internal validation semantic; it does not change the public Contract.

The existing public `Evidence` contract remains unchanged. Internal provenance must
carry the manifest version, source version, checksum, locator, and original
`variant_id`; Product-shared evidence keeps `variant_id = null` even when the Turn
Target has a Variant. No evidence builder may overwrite source scope with target
scope.

## 5. Proposed real-corpus adapter boundary

The bounded data flow is:

```text
RetrievalRequest
  -> CorpusScopeBinding
  -> ControlledRetrievalRequest
  -> ExternalCorpusReader
  -> ExternalCorpusReadResult
  -> RetrievalResult
  -> Evidence Gate
```

`ExternalCorpusReader` is the sole source-region read boundary; the adapter must not
run a second retrieval pass over the same input. `BoundedProductRagLoop` remains the
single owner of Action Round and tool-call budgets. The adapter only translates
validated records and stop reasons and does not increment or reset those budgets.

The internal result must preserve `k`, `max_retrieval_tokens`, `turn_deadline_ms`,
`filtered_out_count`, `manifest_version`, `source_versions`, and a typed stop reason.
`filtered_out_count` is metadata only and never substitutes for an Evidence claim.

The adapter must preserve store/product/variant metadata, source version, locator,
checksum, language, region, and per-record provenance. It must not copy raw PDFs,
official source text, chunks, indexes, embeddings, or training data into Git. It must
not create a vector index or introduce a model, database, or new runtime dependency.

## 6. Canonical-Variant beta boundary

The current S10/S11 beta remains limited to one canonical Variant per Product. No
synthetic secondary Variant may be introduced. A future multi-Variant expansion
requires real Shopify identities and a separate acceptance matrix covering at least
price, inventory, packaging, and bundle-specific facts.

## 7. Non-goals

- No public Contract, Architecture Decision, or Product Behavior change in this
  reconciliation.
- No BM25/embedding/vector database/reranker implementation.
- No model provider, fine-tuning, or agent framework.
- No Shopify access or write operation.
- No Widget, deployment, persistence, or Workflow policy change.
- No change to S11-T04 or any other active S11 Task.

## 8. Open decisions and escalation

Human decision is required before implementation if the adapter needs a new public
Contract, new dependency, different corpus authorization, multi-Variant scope, or a
change to Evidence semantics. The exact external source-region loader remains an
implementation detail only after the approved corpus and checksum gate passes.

## 9. Proposed verification

- Product-shared record is returned for a confirmed Variant request.
- Variant A cannot retrieve Variant B's record.
- Product-only request cannot retrieve Variant-specific or dynamic facts.
- Same-Product static Evidence can coexist with exact-Variant dynamic Shopify Evidence
  without scope mixing.
- Corpus identity resolution is exact and checksum-bound; display-name or fuzzy
  fallback is rejected.
- Manifest/source-version mappings are declared and checksum-valid for every candidate.
- Product-shared Evidence preserves `variant_id = null`; Variant-specific Evidence
  preserves the source Variant ID rather than copying Turn Target scope.
- The adapter performs no second retrieval and leaves Action Round/tool-call accounting
  to `BoundedProductRagLoop`.
- Adapter preserves locator/checksum/provenance and remains ephemeral/read-only.
- Existing S09/S10 tests remain green; no public schema or dependency diff occurs.

See [tasks.md](tasks.md) for bounded, non-executable follow-up tasks.
