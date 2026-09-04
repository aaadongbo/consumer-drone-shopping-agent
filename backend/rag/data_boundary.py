"""S08 repository data-boundary verification helpers."""

from __future__ import annotations

import fnmatch
import subprocess
from collections.abc import Callable, Iterable
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORBIDDEN_PATH_PATTERNS = (
    "*.pdf",
    "**/*.pdf",
    "*raw*official*",
    "**/*raw*official*",
    "*official*text*",
    "**/*official*text*",
    "*shopify*export*",
    "**/*shopify*export*",
    "*embedding*",
    "**/*embedding*",
    "*index*",
    "**/*index*",
    "*golden*",
    "**/*golden*",
    "*training*",
    "**/*training*",
)

FORBIDDEN_PATH_PREFIXES = (
    "Data-Staging/",
    "eval/datasets/",
    "eval/golden/",
    "eval/training/",
    "official-docs/",
    "shopify_exports/",
    "training/",
)

PDF_SIGNATURE = b"%PDF-"
SHOPIFY_EXPORT_SIGNATURES = (
    "Handle,Title," + "Body (HTML),Vendor,Product Category",
    "Variant ID," + "Variant SKU,Variant Inventory Qty",
)
SECRET_SIGNATURES = (
    "-----BEGIN " + "PRIVATE KEY-----",
    "SHOPIFY_ADMIN_" + "API_ACCESS_TOKEN",
    "OPENAI_" + "API_KEY=",
    "sk-" + "proj-",
    "sh" + "pat_",
)
TRAINING_SIGNATURES = (
    '"fine_' + 'tuning"',
    '"training_' + 'file"',
    '"messages"' + ":",
    '"completion"' + ":",
)

DATA_STAGING_MARKERS = (
    "/Users/russeell/Documents/Data-Staging/",
    "Data-Staging/",
)
DATA_STAGING_WRITE_TERMS = (
    " cp ",
    " mv ",
    " rm ",
    " rsync ",
    " tee ",
    " touch ",
    " mkdir ",
    " sed -i",
    ">>",
    ">",
    "--write",
    "write_text",
    "write_bytes",
)
REMOTE_GIT_TERMS = (
    "git push",
    "git fetch",
    "git pull",
    "git clone",
    "git ls-remote",
    "gh pr",
)
SHOPIFY_WRITE_TERMS = (
    "shopify product",
    "shopify inventory",
    "shopify mutation",
    "shopify write",
    "admin/api",
    "-x post",
    "-x put",
    "-x delete",
)


class DataBoundaryViolationReason(StrEnum):
    FORBIDDEN_PATH = "FORBIDDEN_PATH"
    PDF_CONTENT = "PDF_CONTENT"
    SHOPIFY_EXPORT_CONTENT = "SHOPIFY_EXPORT_CONTENT"
    SECRET_CONTENT = "SECRET_CONTENT"
    TRAINING_CONTENT = "TRAINING_CONTENT"
    DATA_STAGING_WRITE_COMMAND = "DATA_STAGING_WRITE_COMMAND"
    REMOTE_GIT_COMMAND = "REMOTE_GIT_COMMAND"
    SHOPIFY_WRITE_COMMAND = "SHOPIFY_WRITE_COMMAND"


class DataBoundaryViolation(BaseModel):
    """One no-upload or zero-write boundary violation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    reason: DataBoundaryViolationReason
    detail: str


class DataBoundaryReport(BaseModel):
    """Internal S08 verification report; not a public wire contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    checked_paths: tuple[str, ...] = ()
    checked_commands: tuple[str, ...] = ()
    violations: tuple[DataBoundaryViolation, ...] = ()
    limit_notes: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_accepted_matches_violations(self) -> DataBoundaryReport:
        if self.accepted == bool(self.violations):
            raise ValueError("accepted must be true only when violations are empty")
        return self


def scan_data_boundary(
    *,
    paths: Iterable[str],
    read_bytes: Callable[[str], bytes | None],
    commands: Iterable[str] = (),
) -> DataBoundaryReport:
    """Scan changed paths and command evidence for S08 no-upload boundaries."""

    checked_paths = tuple(_normalize_path(path) for path in paths)
    checked_commands = tuple(commands)
    violations: list[DataBoundaryViolation] = []

    for path in checked_paths:
        violations.extend(_scan_path(path))
        content = read_bytes(path)
        if content is not None:
            violations.extend(_scan_content(path, content))

    for index, command in enumerate(checked_commands, start=1):
        violations.extend(_scan_command(index, command))

    return DataBoundaryReport(
        accepted=not violations,
        checked_paths=checked_paths,
        checked_commands=checked_commands,
        violations=tuple(violations),
    )


def scan_changed_data_boundary(
    *,
    repo_root: Path,
    base_head: str | None = None,
    snapshot_head: str | None = None,
    commands: Iterable[str] = (),
) -> DataBoundaryReport:
    """Scan current or immutable changed files without creating repo artifacts."""

    changed_paths = _changed_paths(repo_root, base_head, snapshot_head)

    def read_bytes(path: str) -> bytes | None:
        if snapshot_head is not None:
            return _git_show_bytes(repo_root, snapshot_head, path)
        file_path = repo_root / path
        if not file_path.is_file():
            return None
        return file_path.read_bytes()

    return scan_data_boundary(
        paths=changed_paths,
        read_bytes=read_bytes,
        commands=commands,
    )


def report_to_dict(report: DataBoundaryReport) -> dict[str, Any]:
    """Return a JSON-serializable report with stable enum values."""

    return report.model_dump(mode="json")


def _changed_paths(
    repo_root: Path,
    base_head: str | None,
    snapshot_head: str | None,
) -> tuple[str, ...]:
    if (base_head is None) != (snapshot_head is None):
        raise ValueError("base_head and snapshot_head must be supplied together")

    if base_head is not None and snapshot_head is not None:
        args = [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRT",
            f"{base_head}..{snapshot_head}",
        ]
    else:
        return _working_tree_paths(repo_root)

    result = subprocess.run(
        args,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _working_tree_paths(repo_root: Path) -> tuple[str, ...]:
    diff_result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    untracked_result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = {
        line
        for output in (diff_result.stdout, untracked_result.stdout)
        for line in output.splitlines()
        if line
    }
    return tuple(sorted(paths))


def _git_show_bytes(repo_root: Path, snapshot_head: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{snapshot_head}:{path}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _scan_path(path: str) -> list[DataBoundaryViolation]:
    normalized = path.casefold()
    violations: list[DataBoundaryViolation] = []

    for prefix in FORBIDDEN_PATH_PREFIXES:
        if normalized.startswith(prefix.casefold()):
            violations.append(
                DataBoundaryViolation(
                    subject=path,
                    reason=DataBoundaryViolationReason.FORBIDDEN_PATH,
                    detail=f"path prefix is forbidden: {prefix}",
                )
            )

    for pattern in FORBIDDEN_PATH_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern.casefold()):
            violations.append(
                DataBoundaryViolation(
                    subject=path,
                    reason=DataBoundaryViolationReason.FORBIDDEN_PATH,
                    detail=f"path pattern is forbidden: {pattern}",
                )
            )
    return violations


def _scan_content(path: str, content: bytes) -> list[DataBoundaryViolation]:
    violations: list[DataBoundaryViolation] = []
    if content.startswith(PDF_SIGNATURE):
        violations.append(
            DataBoundaryViolation(
                subject=path,
                reason=DataBoundaryViolationReason.PDF_CONTENT,
                detail="file content starts with a PDF signature",
            )
        )

    text = content[:200_000].decode("utf-8", errors="ignore")
    for signature in SHOPIFY_EXPORT_SIGNATURES:
        if signature in text:
            violations.append(
                DataBoundaryViolation(
                    subject=path,
                    reason=DataBoundaryViolationReason.SHOPIFY_EXPORT_CONTENT,
                    detail="content matches a Shopify export signature",
                )
            )
            break

    for signature in SECRET_SIGNATURES:
        if signature in text:
            violations.append(
                DataBoundaryViolation(
                    subject=path,
                    reason=DataBoundaryViolationReason.SECRET_CONTENT,
                    detail="content matches a secret/token signature",
                )
            )
            break

    if _looks_like_training_payload(text):
        violations.append(
            DataBoundaryViolation(
                subject=path,
                reason=DataBoundaryViolationReason.TRAINING_CONTENT,
                detail="content looks like a training or fine-tuning payload",
            )
        )
    return violations


def _scan_command(index: int, command: str) -> list[DataBoundaryViolation]:
    normalized = f" {command.casefold()} "
    subject = f"command[{index}]"
    violations: list[DataBoundaryViolation] = []

    if any(marker.casefold() in normalized for marker in DATA_STAGING_MARKERS) and any(
        term in normalized for term in DATA_STAGING_WRITE_TERMS
    ):
        violations.append(
            DataBoundaryViolation(
                subject=subject,
                reason=DataBoundaryViolationReason.DATA_STAGING_WRITE_COMMAND,
                detail="command appears to write to Data-Staging",
            )
        )

    if any(term in normalized for term in REMOTE_GIT_TERMS):
        violations.append(
            DataBoundaryViolation(
                subject=subject,
                reason=DataBoundaryViolationReason.REMOTE_GIT_COMMAND,
                detail="command appears to perform a remote Git/GitHub operation",
            )
        )

    if "shopify" in normalized and any(
        term in normalized for term in SHOPIFY_WRITE_TERMS
    ):
        violations.append(
            DataBoundaryViolation(
                subject=subject,
                reason=DataBoundaryViolationReason.SHOPIFY_WRITE_COMMAND,
                detail="command appears to perform a Shopify write operation",
            )
        )

    return violations


def _looks_like_training_payload(text: str) -> bool:
    lowered = text.casefold()
    if any(signature in lowered for signature in TRAINING_SIGNATURES[:2]):
        return True
    return ('"messages"' + ":") in lowered and (
        '"role":' in lowered or '"completion":' in lowered
    )


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


__all__ = [
    "FORBIDDEN_PATH_PATTERNS",
    "FORBIDDEN_PATH_PREFIXES",
    "DataBoundaryReport",
    "DataBoundaryViolation",
    "DataBoundaryViolationReason",
    "report_to_dict",
    "scan_changed_data_boundary",
    "scan_data_boundary",
]
