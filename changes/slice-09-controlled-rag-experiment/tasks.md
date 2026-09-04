# Slice 9 Tasks - Controlled RAG Experiment Readiness

> Status: COMPLETED / LOCALLY INTEGRATED
>
> Human accepted this Task table and authorized S09 implementation through completion.
> S09-T01 through T05 are complete, and completion snapshot
> `f222ca2028b9f01dfe32640d7421bd0ffda82651` is integrated into local `main`.
> Remote push and any production-index or serving decision remain separately gated.
> The tasks do not authorize Data-Staging writes, raw-data import, embeddings, indexes,
> training, external services, commits, or pushes.

## Ordered Tasks

| Task | Title | Status | Dependencies |
|---|---|---|---|
| T01 | Corrected chunk-baseline manifest validation | DONE | S08 completion; planning baseline |
| T02 | Ephemeral deterministic chunk metadata experiment | DONE | T01 |
| T03 | Offline scoped lexical retrieval experiment | DONE | T02 |
| T04 | Development evaluation replay and budget gates | DONE | T03 |
| T05 | Controlled RAG readiness handoff | DONE | T04 |

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

## Execution Record

### S09-T01 - DONE

- **Start commit**: `263100c6f7275b7d89242085c485edd09381df30`
- **Scope**: Added internal corrected chunk-baseline manifest validation in
  `backend/rag/chunk_baseline.py`.
- **Result**: Valid append-only metadata manifests are accepted; missing manifests,
  invalid status, missing ordinal/extraction fields, duplicate IDs, checksum-shaped
  errors, and cross-language/region/corpus mismatches fail closed. The model carries
  locator metadata and checksums only, never raw text.
- **Verification**: `tests/unit/test_s09_t01_chunk_baseline.py` included in targeted
  pytest run: `16 passed`.

### S09-T02 - DONE

- **Scope**: Added deterministic ephemeral metadata digest replay through
  `run_ephemeral_chunk_metadata_experiment`.
- **Result**: Same manifest/config produces stable metadata digest and records
  `persisted_to_repository=false`; generated chunk artifacts are not written to the
  repository or Data-Staging.
- **Verification**: T02/T03 integration tests included in targeted pytest run:
  `16 passed`.

### S09-T03 - DONE

- **Scope**: Added `backend/rag/controlled_retrieval.py` for scope-first lexical
  retrieval over corrected chunk metadata.
- **Result**: Retrieval is limited to one store/product/optional variant, returns
  locator/checksum metadata only, rejects cross-product matches before scoring, and
  fails closed for no scoped match, scoped candidate limit, token budget, and deadline.
- **Verification**: T02/T03 integration tests included in targeted pytest run:
  `16 passed`.

### S09-T04 - DONE

- **Scope**: Added development-only replay in `backend/evaluation/s09_replay.py`.
- **Result**: Replay is capped at 15 cases, remains `development_only=true`, never
  freezes a Golden Set, and reports pass/fail against expected locators or explicit
  stop reasons.
- **Verification**: T04/T05 integration tests included in targeted pytest run:
  `16 passed`.

### S09-T05 - DONE

- **Scope**: Added metadata-only GO/HOLD readiness handoff for future production-index
  planning.
- **Result**: Handoff requires complete matrix IDs, accepted chunk baseline,
  successful development replay, and data-boundary acceptance to produce `GO`;
  otherwise it returns `HOLD`. It explicitly defers production index, embeddings,
  reranking, Golden Set freeze, training/fine-tuning, and live Shopify truth.
- **Verification**: T04/T05 integration tests included in targeted pytest run:
  `16 passed`.

### Verification Notes

- Initial `uv run ...` attempts failed because the sandbox could not access the
  default uv cache and then could not download locked packages with a temporary cache.
- Equivalent targeted checks were run with the existing repository virtualenv:
  - Ruff check on changed S09 Python/test files: pass.
  - Ruff format check on changed S09 Python/test files: pass.
  - Targeted pytest for S09 unit/integration tests: `16 passed`.
- S09 changed paths stayed within the S09-T05 Slice completion allowlist.
- No public Contract, core docs, dependency files, Workflow files, raw data, generated
  chunks, embeddings, indexes, training data, Shopify export, Data-Staging write,
  push, or main integration was performed.

### Post-completion Reconciliation

- Local integration: completion snapshot
  `f222ca2028b9f01dfe32640d7421bd0ffda82651` was fast-forward integrated into
  local `main` after the recorded implementation verification.
- Completion-session evidence reported one full-project run with `621 passed`, but
  the per-Task records above retain only the `16 passed` targeted run. Slice 10 must
  therefore record one fresh full baseline with its exact command and exit code before
  real-data implementation begins; it must not repeat that full suite for every Task.
- Remote delivery: not performed; local `main` remains unpushed.
- S09 remains an offline, development-only readiness result and does not claim a
  production RAG index, live Shopify integration, Human-approved Golden Set, or
  production readiness.
