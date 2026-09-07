# Retrieval Upgrade Roadmap — Expert Benchmark to Hybrid Retrieval

> Status: DRAFT / NON-EXECUTABLE / HUMAN REVIEW REQUIRED
>
> This artifact defines a future capability route only. It does not create a
> Slice, formalize Workflow Tasks, authorize implementation, select a model or
> vector provider, access Shopify, write Data-Staging, modify public Contracts,
> or change the approved S11 closed-beta boundary.

## 1. Purpose

The project has a deterministic metadata/keyword retrieval baseline and a
verified Product-shared / Variant-specific scope model. BM25, Embedding,
Hybrid Retrieval, and Reranker remain planned capability directions, but they
must be evaluated against a reproducible benchmark before they are introduced.

The route is deliberately ordered:

\`\`\`text
Expert Golden Set v0.1
        ↓
BM25 baseline
        ↓
Embedding + Hybrid Retrieval
        ↓
Candidate-only Reranker
        ↓
Evidence-based decision on provider and durable state
\`\`\`

The benchmark supports planning and reproducible evaluation design. It does not
authorize engineering implementation, and it must not be described as evidence
of real-user satisfaction until de-identified beta queries are available.

## 2. Current baseline and target state

### Current baseline

- S11 defines the approved closed-beta deployment boundary; this roadmap does
  not assert, reconcile, or reopen S11 task status. Its approved deployment
  path uses a deterministic/restricted intent adapter.
- S09/S10 retrieval is deterministic metadata/keyword overlap with explicit
  identity and Evidence gates; it is not yet BM25, embedding, vector search, or
  reranking.
- Product-shared corpus records may be inherited by a confirmed Variant;
  Variant-specific records and dynamic Shopify facts remain exact-Variant
  scoped.
- The external corpus adapter preserves manifest/source provenance and does not
  imply an index, embedding store, or model provider.
- The beta currently has one canonical Variant per Product. It does not claim
  multi-bundle Variant isolation.

### Target state for this roadmap

The target is a measured retrieval stack in which:

1. BM25 provides a reproducible lexical baseline.
2. Embeddings add semantic candidates without bypassing scope predicates.
3. Hybrid fusion is compared against BM25 on the same frozen benchmark.
4. A reranker orders only the bounded candidate set and never creates facts.
5. Evidence Gate, provenance, budgets, and fallback semantics remain
   authoritative.

No target stage implies public production, Shopify writes, a new public
Contract, or a durable state migration.

## 3. Expert Golden Set v0.1

The first implementation prerequisite is a frozen expert benchmark built from
approved official manuals, FAQ/specification supplements, and the three approved
Shopify Product/Variant identities.

The benchmark should cover, at minimum:

- Product identity and Product-versus-Variant distinction;
- shared specifications, capabilities, safety, manuals, and FAQ;
- Variant-specific packaging, accessories, controller, and battery facts;
- dynamic price, inventory, and availability as non-corpus facts;
- comparison and recommendation prompts;
- Chinese terminology, English terminology, abbreviations, colloquial phrasing,
  typos, and zero-hit cases;
- wrong-Product, wrong-Store, wrong-Variant, ambiguous, and unsupported queries;
- queries where the correct result is clarification or a safe fallback.

Each record should be versioned with metadata equivalent to:

\`\`\`yaml
dataset_version: expert-golden-set-v0.1
query_id: stable-id
query_text_hash: sha256
source_type: expert
store_id: canonical-store-id
product_id: approved-product-id
variant_id: approved-variant-id-or-null
intent: controlled-intent
turn_target: product-or-variant-scope
expected_route: answer|clarify|fallback|commerce-read
expected_evidence_locators: checksum-bound-locator-ids
expected_answer_scope: product|variant|none
difficulty: labeled-level
annotation_status: reviewed|needs-review
evaluator_version: stable-id
\`\`\`

Raw expert query text and any protected source text remain in the external
Data-Staging boundary. Git may contain only an approved manifest, checksums, and
non-sensitive validation metadata after a separate authorization. No raw user
query, token, secret, complete Shopify response, or official full-text copy may
enter Git, logs, or review evidence.

The set is not Golden until every record has a human-reviewed expected route,
scope, and evidence locator, the manifest/checksums are frozen, and the change
log records the evaluator version and reason for each later amendment.

## 4. Retrieval stages and gates

### Stage A — BM25 baseline

Build a local or otherwise controlled lexical index over the already admitted
Product-shared and Variant-specific records. Preserve the existing exact scope
predicate before scoring. The baseline must report at least Recall@k, MRR or
nDCG, evidence/scope correctness, zero-hit and fallback rates, and latency on
the frozen Expert Golden Set.

The index must be reproducible from the admitted manifest and checksum-bound
records. It must not silently ingest unapproved sources, cross Store/Product
records, or promote Variant facts to Product scope.

BM25 is the first independently authorized implementation stage after the
Golden Set. A BM25 result is a baseline, not a claim that lexical retrieval is
adequate.

### Stage B — Embedding and Hybrid Retrieval

Only after the BM25 report is frozen, and under a separate implementation
authorization, evaluate embedding candidates and a
documented fusion method (for example, weighted score fusion or reciprocal-rank
fusion). The comparison must use the same query set, corpus identity, scope
predicate, top-k, token/deadline budgets, and Evidence Gate.

The embedding model/provider, retention, cost, and network boundary remain open
decisions. No external model call, new dependency, vector service, or index
format is authorized by this roadmap. A hybrid result must demonstrate a
measurable benefit over BM25 on the chosen metrics before it replaces the
baseline.

### Stage C — Candidate-only Reranker

Evaluate a reranker only over the bounded BM25/hybrid candidate set. It may
change ordering, but it may not retrieve outside the scope-filtered candidates,
invent evidence, change the answer scope, or bypass budgets and stop reasons.

The reranker is justified only if the benchmark shows that candidate recall is
adequate but ordering/evidence selection remains materially insufficient. Its
provider, model ID, data retention, and cost require a separate decision.

### Stage D — Provider and durable-state decisions

Model Provider selection and Redis/MongoDB adoption are orthogonal to retrieval
quality. They should be considered only after the benchmark and operational
evidence show a need:

- a model provider addresses intent understanding or response expression, with
  deterministic fallback and no unverified facts;
- Redis/MongoDB addresses multi-instance coordination or restart recovery, not
  retrieval recall itself.

Neither is a prerequisite for the BM25 baseline.

## 5. Evaluation contract

Every retrieval stage must use the same frozen identity, evidence, and budget
rules:

- Product requests may read only Product-shared records.
- Confirmed Variant requests may read same-Product shared records plus the exact
  requested Variant records.
- Other Variants, Stores, and Products are rejected before ranking.
- Product-shared Evidence retains \`variant_id = null\`; Variant-specific Evidence
  retains the source Variant ID.
- Dynamic Shopify price, inventory, and availability remain exact-Variant reads;
  static corpus retrieval cannot answer them.
- \`RetrievalResult.index_version\` identifies the admitted manifest identity;
  chunk/source versions remain per-source provenance.
- \`BoundedProductRagLoop\` remains the sole owner of Action Round, tool-call,
  token, and deadline budgets.
- Existing hard limits remain in force unless a separately approved experiment
  changes them: at most 2 Action Rounds, 2 tool calls, 8000 ms turn deadline,
  4000 retrieval tokens, 1200 model tokens, and 10 scoped candidates. A
  reranker may only order that bounded candidate set; it may not expand it.
- Budget exhaustion must preserve the existing stop reasons:
  \`ACTION_ROUND_LIMIT\`, \`TOOL_CALL_LIMIT\`, \`TURN_DEADLINE\`,
  \`RETRIEVAL_TOKEN_BUDGET\`, and \`MODEL_TOKEN_BUDGET\`.

The benchmark report should include, for each stage:

- corpus/manifest identity and evaluator version;
- query count and coverage by intent/scope/difficulty;
- Recall@k and ranking metric(s);
- citation/evidence correctness, answer correctness, and scope-violation count;
- expected-route accuracy, zero-hit/fallback count, and filtered-out count;
- p50/p95 retrieval latency and budget stop reasons;
- unit request cost (compute/provider cost as applicable) and the exact candidate
  cap;
- confidence intervals for paired comparisons against the frozen baseline, with
  a stable net-benefit rule before enabling Hybrid Retrieval or a Reranker;
- reproducibility checksum and known limitations.

Thresholds should be proposed and accepted with the benchmark baseline; this
roadmap intentionally does not invent quality targets before the set is frozen.

## 6. Scope and safety boundaries

This roadmap does not authorize:

- changing S11 Tasks or reopening the closed-beta completion boundary;
- creating Slice 12 or changing Workflow policy;
- public Contract, Architecture, Acceptance, or Accepted Decision changes;
- Shopify write operations, new credentials, or live commerce mutation;
- copying raw corpus/query content, embeddings, indexes, or training data into
  Git;
- introducing dependencies, hosted vector databases, external model calls, or
  durable state without a task-scoped Human decision;
- claiming real-user satisfaction from the Expert Golden Set.

Future work should be a separately authorized delivery scope or planning
baseline, beginning with the Golden Set and BM25. It is an unnumbered future
capability roadmap gated on S11 completion, not a new Slice.

## 7. Review and authorization boundary

This document is ready for independent planning review only. A passing review
does not authorize dataset creation or BM25 implementation.

After review, Human authorization should be granted in two separate decisions:

1. create/freeze \`expert-golden-set-v0.1\` within the approved Data-Staging and
   metadata/checksum boundary;
2. implement and evaluate the BM25 baseline against that frozen set.

The BM25 scope must define exact files, dependency policy, index location,
targeted tests, evidence artifacts, and stop conditions before implementation.
