"""S08 completion matrix for data-backed RAG readiness."""

from pathlib import Path

import pytest

from backend.rag import (
    S08_MATRIX_IDS,
    DataBoundaryViolationReason,
    S08CompletionStatus,
    S08MatrixEvidence,
    build_corpus_readiness_report,
    build_s08_readiness_handoff,
    scan_data_boundary,
)

pytestmark = pytest.mark.e2e


def test_s08_completion_handoff_keeps_corpus_not_indexed_and_deferred() -> None:
    corpus_report = build_corpus_readiness_report()
    boundary_report = scan_data_boundary(
        paths=(
            "backend/rag/s08_readiness.py",
            "tests/e2e/test_s08_t06_completion_matrix.py",
            "changes/slice-08-data-backed-rag/tasks.md",
        ),
        read_bytes=lambda path: (
            Path(path).read_bytes() if Path(path).is_file() else b"metadata-only"
        ),
        commands=(
            "git status --short --branch --untracked-files=all",
            "python scripts/check_s08_data_boundary.py "
            "--base-head 329ce88 --snapshot-head 983aebf",
        ),
    )

    handoff = build_s08_readiness_handoff(
        corpus_report=corpus_report,
        data_boundary_report=boundary_report,
        matrix=_passing_matrix(),
    )

    assert handoff.status is S08CompletionStatus.READY_FOR_HUMAN_HANDOFF
    assert handoff.metadata_accepted is True
    assert handoff.corpus_stop_reason == "CORPUS_NOT_INDEXED"
    assert handoff.data_boundary_accepted is True
    assert "EMBEDDINGS" in handoff.deferred_capabilities
    assert "INDEXES" in handoff.deferred_capabilities
    assert "TRAINING_OR_FINE_TUNING" in handoff.deferred_capabilities
    assert "LIVE_SHOPIFY_TRUTH" in handoff.deferred_capabilities


def test_s08_completion_requires_all_matrix_rows_to_pass() -> None:
    corpus_report = build_corpus_readiness_report()
    boundary_report = scan_data_boundary(
        paths=("backend/rag/s08_readiness.py",),
        read_bytes=lambda path: b"metadata-only",
    )
    matrix = tuple(
        S08MatrixEvidence(
            matrix_id=matrix_id,
            passed=matrix_id != "S08-M07",
            evidence=f"{matrix_id} evidence",
        )
        for matrix_id in S08_MATRIX_IDS
    )

    handoff = build_s08_readiness_handoff(
        corpus_report=corpus_report,
        data_boundary_report=boundary_report,
        matrix=matrix,
    )

    assert handoff.status is S08CompletionStatus.INCOMPLETE


def test_s08_completion_fails_if_forbidden_data_enters_repo_scope() -> None:
    corpus_report = build_corpus_readiness_report()
    boundary_report = scan_data_boundary(
        paths=("tests/fixtures/manual.pdf",),
        read_bytes=lambda path: b"%PDF-1.7",
    )

    handoff = build_s08_readiness_handoff(
        corpus_report=corpus_report,
        data_boundary_report=boundary_report,
        matrix=_passing_matrix(),
    )

    assert handoff.status is S08CompletionStatus.INCOMPLETE
    assert boundary_report.violations[0].reason in {
        DataBoundaryViolationReason.FORBIDDEN_PATH,
        DataBoundaryViolationReason.PDF_CONTENT,
    }


def _passing_matrix() -> tuple[S08MatrixEvidence, ...]:
    return tuple(
        S08MatrixEvidence(
            matrix_id=matrix_id,
            passed=True,
            evidence=f"{matrix_id} targeted verification passed",
        )
        for matrix_id in S08_MATRIX_IDS
    )
