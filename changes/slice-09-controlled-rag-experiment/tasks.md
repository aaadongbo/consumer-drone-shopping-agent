# Slice 9 Tasks - Controlled RAG Experiment Readiness

> Status: PLANNED / non-executable roadmap
>
> These tasks are planning candidates only. They are not formal workflow Tasks and do
> not authorize Data-Staging writes, raw-data import, embeddings, indexes, training,
> external services, commits, or pushes.

## Candidate Roadmap

| Candidate | Title | Roadmap state | Dependencies |
|---|---|---|---|
| S09-T01 | Corrected chunk-baseline manifest validation | CANDIDATE | S08 completion; Human planning approval |
| S09-T02 | Ephemeral deterministic chunk metadata experiment | CANDIDATE | S09-T01 |
| S09-T03 | Offline scoped lexical retrieval experiment | CANDIDATE | S09-T02 |
| S09-T04 | Development evaluation replay and budget gates | CANDIDATE | S09-T03 |
| S09-T05 | Controlled RAG readiness handoff | CANDIDATE | S09-T04 |

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

S09 remains non-executable until Human accepts this table, a separate S09 policy is
activated if needed, and implementation authority is granted. Any public Contract,
Architecture, dependency, external service, production index, embedding, training,
Shopify write, or data-boundary change stops for Human decision.

The table above intentionally does not use the formal workflow Task status column.
If S09 is later activated, a separate governance step must convert these candidates
to formal `NOT_STARTED` rows and add S09 policy coverage. Until then, workflow status
inspection must treat this file as roadmap material only.
