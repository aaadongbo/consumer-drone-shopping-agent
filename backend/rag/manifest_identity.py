"""Internal identity for an admitted external corpus manifest."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from backend.rag.chunk_baseline import ChunkBaselineManifest
from backend.rag.manifest import RagModel

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
type Sha256String = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class CorpusManifestIdentity(RagModel):
    """Stable manifest identity kept separate from each chunk source version."""

    schema_version: NonEmptyString
    corpus_version: NonEmptyString
    manifest_sha256: Sha256String

    @classmethod
    def from_manifest(cls, manifest: ChunkBaselineManifest) -> CorpusManifestIdentity:
        return cls(
            schema_version=manifest.schema_version,
            corpus_version=manifest.corpus_version,
            manifest_sha256=manifest.corpus_manifest_sha256,
        )

    @property
    def index_version(self) -> str:
        """Represent all manifest identity fields in RetrievalResult.index_version."""
        return f"{self.schema_version}:{self.corpus_version}:{self.manifest_sha256}"


__all__ = ["CorpusManifestIdentity"]
