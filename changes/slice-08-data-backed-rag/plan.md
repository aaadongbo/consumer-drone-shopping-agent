# Slice 8 Planning - Data-backed Product RAG Readiness

> Status: PLANNED / non-executable roadmap.
>
> This planning artifact does not authorize implementation, workflow-policy creation,
> task execution, dependency installation, Shopify access, embedding/index serving,
> training, fine-tuning, commit, push, or remote Git operations. Start S08-T01 only
> after Human Review, a planning baseline decision, and any separately approved
> workflow policy or implementation authority.

## 1. Read-only Planning Baseline

- Repository inspection: current planning checkout is detached at
  `7207a2b6e7931c9e9edbd22ee850aea1fdc51c5a`; `git status --short --branch`
  reported `## HEAD (no branch)` and no dirty paths.
- Main worktree inspection via workflow helper: `/Users/russeell/Documents/ChatGPT/消费级无人机智能导购Agent`
  is on `refs/heads/main` at the same HEAD and clean.
- Remotes observed read-only: `origin` points to
  `aaadongbo/consumer-drone-shopping-agent`; `russeell-origin` points to
  `russeell/consumer-drone-shopping-agent`. No fetch, push, branch, PR, or remote
  mutation was performed.
- Slice state: Slice 1 through Slice 7 task tables are all `DONE`; the workflow
  helper reports active tasks `[]`, ready tasks `[]`, selected task `null`, and no
  current executable task.
- Existing S05/S06 implementation is already a lightweight in-memory Product RAG
  and Evidence Recommendation skeleton, not a production retrieval service.

## 2. Data Readiness Findings

All source data below lives outside the repository under
`/Users/russeell/Documents/Data-Staging/consumer-drone-agent`. These paths are
referenced for planning only. They must not be uploaded to `russeell` GitHub, copied
into the public repository, or promoted to training data by this Slice.

| Input | Path / binding | Finding | S08 planning implication |
|---|---|---|---|
| Synthetic readiness v0.2.1 | `outputs/data-readiness-20260830-v2.1/human_review.synthetic.v0.2.1.json` | `overall_decision=APPROVED_WITH_LIMITED_SCOPE`; validation was `PASS_WITH_HUMAN_REVIEW_REQUIRED`; approved only for limited deterministic fixture/eval use. | Can inform deterministic fixture shape, but not a real-data corpus or training set. |
| Shopify DJI snapshot v0.3 | `outputs/shopify-dji-snapshot-20260831-v0.3/manifest.json` | `status=CANDIDATE_WITH_LIMITATIONS`; 3 products, 3 variants, 20 images; `variant_id_status=UNRESOLVED_FROM_STANDARD_EXPORT`; human review still required for limitations. | May be used only as candidate dynamic/static boundary input. Must not be treated as current Shopify truth or approved production data. |
| Raw user-supplied DJI manuals | `source_documents/dji_manuals/manifest.json` | `status=RAW_UNVERIFIED`; three zh-CN PDFs are user supplied, with page counts and SHA-256; official source not independently verified in that manifest. | Do not ingest from this raw collection directly; use reviewed corpus bindings only. |
| RAG corpus v0.1 | `outputs/rag-corpus-20260902-v0.1/manifest.json` | `status=ADMITTED_SOURCE_CORPUS__LOCATORS_INCLUDED__NOT_INDEXED`; immutable; 3 sources, 261 page locators, `chunks=0`, `embeddings=0`, `indexes=0`, `retrieval_runs=0`, `golden_set_frozen=false`. | Best S08 input for a controlled repository adapter/readiness layer. It is not an index and cannot serve retrieval yet. |
| RAG corpus derived locators | `outputs/rag-corpus-20260902-v0.1/derived/page_locators/*.jsonl` and `derived/mavic_3_scope_overlay.v0.1.json` | 66 Mini 3, 109 Air 3, 86 Mavic 3 locator records; Mavic 3/Cine excluded by overlay. | S08 can validate metadata/source binding and create a walking skeleton from page locator records only after explicit authorization. |
| Chunking review v0.3 | `outputs/rag-chunking-ablation-20260902-v0.3/human_review.chunking-baseline.v0.1.json` | Directory contains the independent review sidecar only; no manifest or regenerated chunk output was found. Review status is `AI_REVIEW_NEEDS_CHANGES`, with blocker CB-001 on missing `ordinal_start`, `ordinal_end`, `extraction_method`. | Must not be written as an approved baseline. S08 can plan to reject/skip old chunk artifacts until a new append-only corrected output exists. |
| Retrieval eval readiness v0.1 | `outputs/rag-retrieval-eval-readiness-20260901-v0.1/manifest.json` | `DEVELOPMENT_PROTOCOL_PREPARED__ANNOTATION_AND_HUMAN_APPROVAL_REQUIRED`; 15 questions, 0 annotated, no embeddings/indexes/retrieval runs, golden set not frozen. | Can define non-frozen dev-case shape; cannot gate production quality or freeze Golden Set. |
| Offline retrieval ablation v0.1 | `outputs/rag-offline-retrieval-ablation-20260901-v0.1/manifest.json` | `DEVELOPMENT_ONLY__HUMAN_REVIEW_REQUIRED`; lexical experiment and provisional gold page annotations exist. | Useful as prior evidence only; S08 must require human review before baseline promotion. |
| Official verification sidecars | `outputs/rag-source-official-verification-20260901-v0.1/*v0.3.json` | Corpus manifest binds to v0.3 official/copyright/human review records. | S08 must preserve authorization/source bindings and never silently broaden scope. |

Observed blockers and unfinished items:

- Candidate corpus v0.1 is not indexed and has no chunks or embeddings in the
  corpus manifest.
- Chunking review is `AI_REVIEW_NEEDS_CHANGES`; no S08 work may claim Arm A/B/C as
  Human-approved baseline.
- Shopify v0.3 is still a candidate with limitations and unresolved Variant ID
  status from standard export.
- Retrieval development labels are not Human-reviewed Golden Set.
- Training and fine-tuning remain `DEFERRED_NOT_AUTHORIZED`.

## 3. Goal

Create a minimal, data-backed readiness path that lets the existing Product RAG
semantics consume externally staged, reviewed corpus metadata safely: validate corpus
manifest/source/page-locator bindings, enforce one Turn Target Product/Variant scope,
separate static RAG from dynamic Shopify facts, and fail closed when corpus/index data
is stale, invalid, unapproved, or absent.

This is deliberately narrower than production RAG. Slice 8 should first build an
offline walking skeleton around manifest and locator readiness; only after Human
approval should it consider controlled retrieval integration. It is not a training
Slice.

## 4. Product Behavior

In scope:

- Product RAG for one resolved Turn Target only: one store, one product, optional one
  variant.
- Source scope fixed to zh-CN / China mainland official-source candidate bindings for
  DJI Mini 3, DJI Air 3, and standard DJI Mavic 3 only.
- Metadata/source binding validation before any chunk or retrieval result is accepted.
- Citation locator validation against source ID, version, page locator, product scope,
  language, region, and Mavic 3/Cine overlay.
- Abstention/no-answer when evidence is missing, scope-mismatched, stale, invalid, or
  dynamic-commerce-only.
- Zero writes to Shopify, Data-Staging, and remote Git during implementation unless a
  future task explicitly authorizes a repository-local fixture or adapter file.

Non-goals:

- Training, fine-tuning, Golden Set freeze, embedding productionization, hosted index
  serving, Milvus adoption, reranker selection, or new Agent framework.
- Multi-product comparison/recommendation RAG allocation, Shopify write operations,
  storefront/widget changes, cart/order/customer capabilities, open-web evidence, or
  after-sales/legal authority answers.
- Changing existing public wire contracts, Architecture, Accepted Decisions, Workflow
  policy, or Slice 1-7 plan/tasks.
- Copying raw PDFs, staging corpora, Shopify exports, official documents, or training
  data into the public repository.

## 5. Acceptance

| ID | Acceptance | PASS condition |
|---|---|---|
| S8-A01 | Metadata/source binding | Every accepted source, locator, chunk candidate, and citation binds to the staged corpus manifest path, file checksum, source_ref, product scope, language, region, and document version. |
| S8-A02 | Product scope filter | Retrieval/readiness candidates are hard-filtered to one Turn Target store/product/optional variant before scoring or answer composition; cross-product records are rejected. |
| S8-A03 | Citation locator | Any answerable static claim must include a locator that resolves to a known source/page record and survives Mavic 3/Cine overlay checks. |
| S8-A04 | Abstention/no-answer | Missing support, no scoped hit, ambiguous Mavic 3/Cine source, unreviewed chunk baseline, or dynamic-commerce-only question returns a structured fallback, not model common knowledge. |
| S8-A05 | Stale/invalid corpus | Missing manifest, checksum mismatch, old chunk artifact without required metadata, unapproved review status, or corpus version mismatch prevents retrieval integration and reports an exact stop reason. |
| S8-A06 | Dynamic/static split | Price, inventory, availability, current sale status, and Shopify Variant truth are never answered from static RAG corpus or staging snapshots. |
| S8-A07 | Shopify candidate limits | Shopify v0.3 remains candidate-with-limitations; unresolved or stale Variant ID evidence cannot be promoted to current commerce truth. |
| S8-A08 | Zero-write boundary | S08 implementation performs no Shopify writes, no Data-Staging mutation, no Git remote operations, and no secret logging; tests prove write-call count is zero. |
| S8-A09 | No training misuse | No staged corpus, eval cases, Shopify export, or answer trace is labeled or exported as training/fine-tuning data. |
| S8-A10 | No upload constraint | Repository changes contain only code/tests/docs explicitly authorized for S08 and never include raw PDFs, Shopify exports, official documents, staging outputs, embeddings, indexes, or training files. |
| S8-A11 | Bounded budget | Retrieval/readiness flow respects the provisional budget and stops with an exact reason when the limit is hit. |
| S8-A12 | Existing contract compatibility | Any public schema expansion is deferred to Human reconciliation; S08 uses internal semantics or existing Evidence/Answer fallback shapes only. |

## 6. Minimal Contracts

S08 should avoid broad public wire changes. Needed semantics are internal or adapter
level unless a later Human decision approves otherwise:

- Existing `DocumentSource`, `DocumentChunk`, `SourceLocator`, `DocumentManifest`:
  keep store/product/variant/source/version/locator authorization semantics.
- Existing `RetrievalRequest` and `RetrievalResult`: continue binding to `ObjectScope`,
  question, `k`, strategy, index/version, evidence, filtered count, and missing reason.
- New internal `CorpusReadinessReport`: staged manifest path, manifest checksum,
  corpus_version, counts, review bindings, accepted/rejected files, stop reason.
- New internal `LocatorBinding`: source_ref, source_id, version, page_number,
  locator, product_scope, language, region, checksum, overlay decision.
- New internal stop reasons: `CORPUS_NOT_INDEXED`, `CORPUS_MANIFEST_MISSING`,
  `CORPUS_CHECKSUM_MISMATCH`, `CHUNK_BASELINE_NEEDS_CHANGES`,
  `LOCATOR_SCOPE_MISMATCH`, `DYNAMIC_FACT_REQUIRED`, `GOLDEN_SET_NOT_FROZEN`,
  `TRAINING_NOT_AUTHORIZED`.
- Existing fallback/evidence semantics should be reused. A RAG-specific public
  `EvidenceType` or client payload extension is an Open Decision, not part of this
  planning baseline.

## 7. Provisional Budget

Defaults for the future executable Slice:

| Key | Default | Stop reason |
|---|---:|---|
| `max_action_rounds` | `2` total | `ACTION_ROUND_LIMIT` |
| `max_tool_calls` | `2` per turn | `TOOL_CALL_LIMIT` |
| `turn_deadline_ms` | `8000` | `TURN_DEADLINE` |
| `max_retrieval_tokens` | `4000` per turn | `RETRIEVAL_TOKEN_BUDGET` |
| `max_model_tokens` | `1200` per turn | `MODEL_TOKEN_BUDGET` |
| `max_staged_locator_records_loaded` | `300` | `LOCATOR_RECORD_LIMIT` |
| `max_scoped_candidates` | `10` | `SCOPED_CANDIDATE_LIMIT` |

Open budget values may be tightened after Human Review, but execution should start
from these defaults and fail closed if a value is missing.

## 8. Verification Matrix

| Matrix | Scenario | Expected |
|---:|---|---|
| 1 | Valid corpus v0.1 manifest and 261 page locators | Readiness report accepts manifest/locator metadata but reports `CORPUS_NOT_INDEXED` for serving. |
| 2 | Missing `rag-chunking-ablation-20260902-v0.3/manifest.json` | Exact invalid-baseline stop reason; no baseline promotion. |
| 3 | Chunk review status `AI_REVIEW_NEEDS_CHANGES` | Retrieval integration is blocked until corrected append-only chunk output exists. |
| 4 | Mini 3 target asks static manual fact with matching locator | Candidate evidence/citation binds only to Mini 3 source/version/page. |
| 5 | Air 3 target receives Mini 3 locator injection | Scope gate rejects before answer composition. |
| 6 | Standard Mavic 3 target hits Cine overlay page | Abstention or clarification; no standard Mavic 3 claim. |
| 7 | User asks price/inventory/availability | Dynamic-commerce fallback/handoff; no static RAG answer. |
| 8 | Shopify v0.3 stale or unresolved Variant ID used as current truth | Rejected; candidate limitation surfaced. |
| 9 | Retrieval dev protocol has 15 questions but 0 annotated | Golden Set remains unfrozen; no production metric claim. |
| 10 | Attempted staged PDF/export inclusion in repo diff | Verification fails no-upload constraint. |
| 11 | Training/fine-tuning export path appears | Verification fails with `TRAINING_NOT_AUTHORIZED`. |
| 12 | Zero-write audit | No Shopify write methods, no Data-Staging writes, no remote Git commands. |

## 9. Human Escalation Conditions

Stop and request a current-context Human decision before:

- Changing public `AnswerEnvelope`, Evidence wire schema, Architecture, Accepted
  Decision status, Workflow policy, or Slice 1-7 artifacts.
- Treating chunking Arm A/B/C as approved baseline, freezing Golden Set, or promoting
  development-only metrics.
- Creating embeddings, indexes, retrieval serving, hosted infrastructure, reranker,
  Milvus dependency, or external CI gate.
- Reading live Shopify credentials, performing Shopify OAuth/smoke, or using Shopify
  v0.3 as current commerce truth.
- Expanding corpus beyond the three reviewed zh-CN / China mainland manuals, changing
  Mavic 3/Cine policy, or using open-web/community content as evidence.
- Copying raw PDFs, staging corpora, Shopify exports, official documents, or training
  data into the repository or pushing anything to `russeell-origin`.

## 10. Open Decisions

- `OD-S08-01`: Whether a corrected append-only chunk output should be generated before
  S08 starts, or S08 should only validate corpus/page locators first.
- `OD-S08-02`: Whether Arm A can become the first non-production candidate after
  CB-001/CB-004 fixes and Human review.
- `OD-S08-03`: Whether S08 needs a repository-local tiny fixture derived from staging
  metadata only, or should keep all real corpus reads external to the repo.
- `OD-S08-04`: Whether a RAG-specific public `EvidenceType` is needed, or existing
  tool evidence remains sufficient for V1.
- `OD-S08-05`: Minimum Human-reviewed dev-case coverage before any index experiment.

## 11. Staging / Repository Boundary

Reference only from Data-Staging:

- RAG corpus manifests, source inventory, page locators, scope overlay, official
  verification sidecars, Shopify candidate snapshots, synthetic readiness artifacts,
  and retrieval development artifacts.

May enter the repository only after separate Human approval:

- Small synthetic or metadata-only fixtures that contain no official document text,
  no raw PDFs, no Shopify export rows, no images, no embeddings, no indexes, no
  credentials, and no training examples.

Must not enter the repository:

- Raw DJI PDFs, copied official document text, Shopify CSV exports, full staging
  outputs, generated embeddings, vector/BM25 indexes, live tokens, secrets, training
  data, fine-tuning files, or Golden Set labels before a Human freeze decision.

## 12. Recommended Next Step

1. Human Review this S08 planning artifact and the referenced staging findings.
2. If accepted, establish a planning baseline without starting S08-T01.
3. Decide whether S08 needs a separate workflow policy; create it only in a dedicated
   governance session if necessary.
4. Separately authorize S08-T01, beginning with offline manifest/locator readiness
   validation only.
