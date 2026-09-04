# Slice 9 Tasks - Controlled RAG Experiment Readiness

> Status: APPROVED IMPLEMENTATION BASELINE / NOT_STARTED
>
> Human has accepted this Task table. S09 Workflow Policy is activated for fail-closed
> routing; formal implementation authority is still required before S09-T01 runs.
> The tasks do not authorize Data-Staging writes, raw-data import, embeddings, indexes,
> training, external services, commits, or pushes.

## Ordered Tasks

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Corrected chunk-baseline manifest validation | NOT_STARTED | S08 completion; planning baseline |
| T02 | Ephemeral deterministic chunk metadata experiment | NOT_STARTED | T01 |
| T03 | Offline scoped lexical retrieval experiment | NOT_STARTED | T02 |
| T04 | Development evaluation replay and budget gates | NOT_STARTED | T03 |
| T05 | Controlled RAG readiness handoff | NOT_STARTED | T04 |

## Task Boundaries

### S09-T01 - Corrected Chunk-baseline Manifest Validation

- **Goal**: Validate an append-only corrected chunk manifest and provenance bindings.
- **Scope**: External metadata/manifests only; source/page/version/checksum/overlay fields.
- **Acceptance**: Missing extraction ordinals, invalid status, checksum mismatch, and
  cross-scope bindings fail closed; no raw content enters the repository.
- **Verification**: Metadata fixture unit/contract tests and read-only staging checks.
- **Out of Scope**: Chunk text import, embeddings, index creation, serving, training.

### S09-T02 - Ephemeral Deterministic Chunk Metadata Experiment

- **Goal**: Generate and inspect chunk metadata in a temporary workspace without
  persisting raw text or artifacts in the repository.
- **Scope**: Deterministic boundaries, ordinals, source locators, checksums, and counts.
- **Acceptance**: Same input/config replays identically; malformed or mixed-source
  records are rejected before retrieval.
- **Verification**: Unit tests, replay digest, and no-upload/data-boundary scan.
- **Out of Scope**: Data-Staging mutation, repository chunk files, embeddings/indexes.

### S09-T03 - Offline Scoped Lexical Retrieval Experiment

- **Goal**: Run a bounded lexical/metadata retrieval experiment for one Turn Target.
- **Scope**: In-memory or ephemeral local index over an externally staged,
  append-only corrected chunk baseline that has passed S09-T01. The repository stores
  only metadata, locators, checksums, counts, metrics, and stop reasons. Raw PDFs,
  official full text, generated chunk files, embeddings, and indexes remain outside
  the repository and must not be pushed.
- **Acceptance**: Only correctly bound locators are returned; no match yields an explicit
  stop reason; replay ordering is stable.
- **Verification**: Integration tests for product/variant isolation, overlay rejection,
  deterministic replay, and budget exhaustion.
- **Out of Scope**: Multi-product retrieval, vector DB, hosted serving, reranker.

### S09-T04 - Development Evaluation Replay and Budget Gates

- **Goal**: Replay the non-frozen development cases and report bounded metrics.
- **Scope**: Existing 15-case development protocol, retrieval/locator metrics, budget
  and stop reasons.
- **Acceptance**: Metrics are labeled development-only; unfrozen cases cannot authorize
  production claims, Golden Set freeze, or training.
- **Verification**: Evaluation replay, schema checks, and trace/data-boundary checks.
- **Out of Scope**: Human Golden Set freeze, model training, production SLO claims.

### S09-T05 - Controlled RAG Readiness Handoff

- **Goal**: Consolidate evidence and decide GO/HOLD for a future production-index Slice.
- **Scope**: Matrix replay, provenance summary, budget results, unresolved decisions,
  and explicit deferred capabilities.
- **Acceptance**: Handoff is reproducible, contains no raw data, and does not claim
  production readiness or Human approval.
- **Verification**: Full S09 matrix, relevant existing tests, data-boundary scan, and
  final read-only review of the handoff.
- **Out of Scope**: Production index/serving, public Contract, Shopify, training, push.

## Workflow and Authority

S09 task execution requires current-context implementation authority. Any public Contract,
Architecture, dependency, external service, production index, embedding, training,
Shopify write, or data-boundary change stops for Human decision.
