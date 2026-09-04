# Slice 9 Plan - Controlled RAG Experiment Readiness

> Status: PLANNED / non-executable roadmap
>
> This Slice follows S08's `CORPUS_NOT_INDEXED` handoff. It prepares a bounded,
> reproducible offline retrieval experiment from reviewed metadata, but does not
> promote a production index or change public contracts.

## 1. Goal

Establish enough corrected chunk metadata, deterministic offline retrieval evidence,
and evaluation readiness to decide whether a later production RAG Slice is justified.
The experiment must remain reproducible, single-target, and outside the repository's
raw-data boundary.

## 2. Scope

In scope:

- Validate a new append-only chunk-baseline manifest and its source/page/overlay
  bindings against `rag-corpus-20260902-v0.1`.
- Run deterministic lexical or metadata retrieval in an ephemeral workspace using the
  reviewed zh-CN / China-mainland corpus scope.
- Measure scope precision, locator integrity, deterministic replay, and bounded budget
  behavior for a non-frozen development set.
- Produce metadata-only readiness reports, checksums, counts, and evaluation summaries
  that contain no copied official text or raw source files in this repository.
- Define the decision evidence needed before any embedding, persistent index, or
  production serving work.

Out of scope:

- Milvus, hosted vector/BM25 services, persistent production indexes, or online serving.
- Embedding generation, reranking, fine-tuning, training, or Golden Set freeze.
- Live Shopify access, current commerce truth, Shopify exports, or Shopify writes.
- Public Contract, Architecture, Accepted Decision, Widget, API, or dependency changes.
- Open-web/community retrieval, multi-product retrieval, or unrestricted corpus scope.
- Copying PDFs, official document text, full staging outputs, chunks, embeddings, or
  indexes into the repository or pushing them to GitHub.

## 3. Product and Evidence Boundary

- Retrieval is limited to one resolved Turn Target: one store, one product, and
  optional one variant, in the reviewed zh-CN / China-mainland scope.
- Every candidate carries source version, page locator, product scope, overlay decision,
  and checksum provenance. Invalid or mixed provenance is rejected before scoring.
- Lexical retrieval, if attempted, reads only an externally staged corrected chunk
  baseline that has passed append-only manifest validation in this Slice. It must not
  read raw PDFs or unbounded official full text directly, and it must not persist chunk
  text, generated retrieval indexes, or copied source content in this repository.
- If the corrected chunk baseline is missing, rejected, or not checksum-bound to the
  admitted corpus, the experiment stops with `CHUNK_BASELINE_REQUIRED` or the more
  specific validation reason instead of falling back to raw documents.
- Static document evidence cannot answer dynamic commerce facts; those remain Shopify
  read operations in the existing architecture.
- Development metrics are advisory only and cannot be presented as production quality
  or a frozen Golden Set.

## 4. Acceptance Criteria

1. A corrected chunk manifest is append-only, checksum-bound to the admitted corpus,
   and rejects missing `ordinal_start`, `ordinal_end`, or `extraction_method`.
2. Cross-product, cross-language, cross-region, source-version, and Mavic 3/Cine
   overlay mismatches fail closed before retrieval scoring.
3. The offline retrieval experiment is deterministic for the same input, config, and
   corpus version; replay produces the same ordered locator IDs and metadata digest.
4. Retrieval returns only candidates inside the Turn Target scope, or an explicit
   `NO_SCOPED_MATCH` / `CORPUS_NOT_INDEXED` stop reason.
5. A development evaluation set remains explicitly non-frozen; no result claims
   production precision/recall or authorizes training.
6. Hard limits are enforced and observable: at most 2 retrieval passes, 10 scoped
   candidates, 4,000 retrieval tokens, and 8,000 ms turn budget.
7. No repository diff contains raw PDFs, official text, Shopify exports, staging
   outputs, chunks, embeddings, indexes, secrets, or training data.
8. No public Contract, Architecture, dependency, external service, Shopify write, or
   production-serving behavior changes are required.
9. The final handoff lists unresolved decisions and gives a clear GO / HOLD decision
   for a future production-index Slice without claiming Human approval.

## 5. Provisional Experiment Budget

| Key | Limit | Stop reason |
|---|---:|---|
| `max_action_rounds` | 2 total | `ACTION_ROUND_LIMIT` |
| `max_scoped_candidates` | 10 | `SCOPED_CANDIDATE_LIMIT` |
| `max_retrieval_tokens` | 4000 | `RETRIEVAL_TOKEN_BUDGET` |
| `turn_deadline_ms` | 8000 | `TURN_DEADLINE` |
| `max_dev_cases` | 15 | `DEV_CASE_LIMIT` |

These are provisional hard limits for the offline experiment, not production SLOs.

`max_action_rounds` and retrieval passes use the same counter: round 1 is the baseline
scoped lexical/metadata retrieval pass, and round 2 is the only allowed corrective
pass when round 1 fails coverage or scope verification. There is no separate
"initial retrieval plus two corrections" interpretation.

`max_retrieval_tokens` is counted over candidate text loaded into the ephemeral
experiment workspace before scoring or replay reporting. Until a production tokenizer
is approved, S09 uses a deterministic standard-library estimator documented in the
experiment report; missing or unreported token counting stops with
`RETRIEVAL_TOKEN_BUDGET`.

## 6. Human Escalation Conditions

Stop for a current-context Human decision before:

- Promoting a chunking arm or development metric to an approved baseline.
- Generating embeddings, creating a persistent/hosted index, adding Milvus, or serving
  retrieval online.
- Freezing a Golden Set, exporting training data, or fine-tuning a model.
- Expanding beyond the reviewed corpus/scope or changing Mavic 3/Cine policy.
- Reading live Shopify credentials, using candidate Shopify snapshots as truth, or
  performing any Shopify/Data-Staging write.
- Changing public schemas, Architecture, Accepted Decisions, dependencies, or Workflow.

## 7. Open Decisions

- Whether the corrected chunk manifest is sufficient for a non-production experiment.
- Whether lexical-only retrieval is adequate before any embedding investment.
- Which of the 15 development cases may receive Human-reviewed annotations.
- Whether a future production Slice should use an existing Evidence type or propose a
  versioned RAG-specific Evidence field.

## 8. Recommended Next Step

Human should review this planning boundary and, if accepted, create a separate S09
Workflow Policy only if the formal tasks need execution routing. No S09 task is
executable until the task table is formalized and separately authorized.
