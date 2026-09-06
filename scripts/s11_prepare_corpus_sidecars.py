"""Prepare persistent corpus decision sidecars before the S11 service starts.

Render executes the pre-deploy command without reliably preserving shell
operators.  Keeping this operation in a small, idempotent Python entrypoint
ensures that only the approved metadata sidecars are linked into the paths
referenced by the corpus manifest.  No credentials or source contents are
read or emitted.
"""

from __future__ import annotations

from pathlib import Path

CORPUS_ROOT = Path("/var/data/drone-corpus")
SIDECAR_ROOT = CORPUS_ROOT / "sidecars"

_LINKS = {
    Path("/var/data/rag-source-official-verification-20260901-v0.1")
    / "copyright_policy_gate.v0.3.json": SIDECAR_ROOT
    / "rag-source-official-verification-20260901-v0.1"
    / "copyright_policy_gate.v0.3.json",
    Path("/var/data/rag-source-official-verification-20260901-v0.1")
    / "human_review.rag-source-official-verification.v0.3.json": SIDECAR_ROOT
    / "rag-source-official-verification-20260901-v0.1"
    / "human_review.rag-source-official-verification.v0.3.json",
    Path("/var/data/rag-source-authorized-staging-20260901-v0.1")
    / "manifest.json": SIDECAR_ROOT
    / "rag-source-authorized-staging-20260901-v0.1"
    / "manifest.json",
}


def prepare() -> None:
    """Create the manifest-referenced directories and metadata-only links."""

    if not CORPUS_ROOT.is_dir():
        raise SystemExit("corpus root is unavailable")
    if not SIDECAR_ROOT.is_dir():
        raise SystemExit("corpus sidecar directory is unavailable")

    for destination, source in _LINKS.items():
        if not source.is_file():
            raise SystemExit(f"required sidecar is unavailable: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or destination.exists():
            destination.unlink()
        destination.symlink_to(source)


if __name__ == "__main__":
    prepare()
