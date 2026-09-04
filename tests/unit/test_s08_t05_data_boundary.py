from __future__ import annotations

import pytest

from backend.rag.data_boundary import (
    DataBoundaryViolationReason,
    scan_data_boundary,
)

pytestmark = pytest.mark.unit


def _scan(paths: dict[str, bytes], commands: tuple[str, ...] = ()):
    return scan_data_boundary(
        paths=paths.keys(),
        read_bytes=lambda path: paths.get(path),
        commands=commands,
    )


def test_metadata_only_s08_paths_are_accepted() -> None:
    report = _scan(
        {
            "backend/rag/data_boundary.py": b"internal metadata helper",
            "scripts/check_s08_data_boundary.py": b"print metadata report",
            "tests/unit/test_s08_t05_data_boundary.py": b"small synthetic fixture",
        },
        commands=(
            "git status --short --branch --untracked-files=all",
            'python -c "from backend.rag import build_corpus_readiness_report"',
        ),
    )

    assert report.accepted is True
    assert report.violations == ()


def test_forbidden_pdf_path_fails_even_for_small_fixture() -> None:
    report = _scan({"tests/fixtures/manual.pdf": b"not a real pdf"})

    assert report.accepted is False
    assert report.violations[0].reason == DataBoundaryViolationReason.FORBIDDEN_PATH


def test_pdf_content_signature_fails_on_non_pdf_extension() -> None:
    report = _scan({"tests/fixtures/manual_metadata.txt": b"%PDF-1.7"})

    assert report.accepted is False
    assert report.violations[0].reason == DataBoundaryViolationReason.PDF_CONTENT


def test_shopify_export_path_and_content_fail() -> None:
    report = _scan(
        {
            "tests/fixtures/shopify_export_sample.csv": (
                b"Handle,Title," + b"Body (HTML),Vendor,Product Category\n"
            )
        }
    )

    reasons = {violation.reason for violation in report.violations}
    assert DataBoundaryViolationReason.FORBIDDEN_PATH in reasons
    assert DataBoundaryViolationReason.SHOPIFY_EXPORT_CONTENT in reasons


def test_secret_and_training_payloads_fail() -> None:
    report = _scan(
        {
            "tests/fixtures/token_metadata.txt": (
                ("OPENAI_" + "API_KEY=sk-" + "proj-example").encode()
            ),
            "tests/fixtures/synthetic_examples.jsonl": (
                ('{"' + 'messages":[{"role":"user","content":"hello"}]}').encode()
            ),
        }
    )

    reasons = {violation.reason for violation in report.violations}
    assert DataBoundaryViolationReason.SECRET_CONTENT in reasons
    assert DataBoundaryViolationReason.TRAINING_CONTENT in reasons


def test_forbidden_embedding_index_golden_and_training_paths_fail() -> None:
    report = _scan(
        {
            "backend/rag/product_embedding_fixture.json": b"{}",
            "backend/rag/offline_index_fixture.json": b"{}",
            "eval/golden/s08_cases.json": b"{}",
            "training/fine_tuning.jsonl": b"{}",
        }
    )

    assert report.accepted is False
    assert all(
        violation.reason == DataBoundaryViolationReason.FORBIDDEN_PATH
        for violation in report.violations
    )


def test_command_log_flags_zero_write_boundary_violations() -> None:
    report = _scan(
        {"backend/rag/data_boundary.py": b"metadata"},
        commands=(
            "cp fixture /Users/russeell/Documents/Data-Staging/consumer-drone-agent/x",
            "git push origin codex/s08-implementation",
            "shopify product update 123 --title test",
        ),
    )

    reasons = {violation.reason for violation in report.violations}
    assert DataBoundaryViolationReason.DATA_STAGING_WRITE_COMMAND in reasons
    assert DataBoundaryViolationReason.REMOTE_GIT_COMMAND in reasons
    assert DataBoundaryViolationReason.SHOPIFY_WRITE_COMMAND in reasons


def test_data_staging_read_only_command_is_allowed() -> None:
    command = (
        "python -c \"Path('/Users/russeell/Documents/Data-Staging/"
        "consumer-drone-agent').exists()\""
    )
    report = _scan(
        {"backend/rag/data_boundary.py": b"metadata"},
        commands=(command,),
    )

    assert report.accepted is True
