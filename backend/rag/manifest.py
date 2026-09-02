"""Slice 5 document manifest and source provenance contracts."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class RagModel(BaseModel):
    """Strict internal model for deterministic Product RAG fixtures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class AuthorizationState(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    UNAUTHORIZED = "UNAUTHORIZED"


class DocumentSourceType(StrEnum):
    FAQ = "FAQ"
    PACKAGE_LIST = "PACKAGE_LIST"
    MANUAL = "MANUAL"
    POLICY = "POLICY"


class SourceLocator(RagModel):
    """Canonical locator for replaying evidence back to one source region."""

    source_id: NonEmptyString
    version: NonEmptyString
    locator: NonEmptyString

    @model_validator(mode="after")
    def validate_canonical_locator(self) -> "SourceLocator":
        expected_prefix = f"rag://{self.source_id}@{self.version}/"
        if not self.locator.startswith(expected_prefix):
            raise ValueError("locator must start with rag://<source_id>@<version>/")
        return self


class DocumentSource(RagModel):
    """One merchant-authorized static document in a single product scope."""

    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    source_id: NonEmptyString
    source_type: DocumentSourceType
    version: NonEmptyString
    canonical_locator: NonEmptyString
    authorization_state: AuthorizationState
    title: NonEmptyString
    text: NonEmptyString
    metadata: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_shape(self) -> "DocumentSource":
        expected_prefix = f"rag://{self.source_id}@{self.version}/"
        if not self.canonical_locator.startswith(expected_prefix):
            raise ValueError(
                "canonical_locator must start with rag://<source_id>@<version>/"
            )
        return self

    def locator(self, path: str) -> SourceLocator:
        clean_path = path.strip().lstrip("/")
        if not clean_path:
            raise ValueError("locator path must be non-empty")
        return SourceLocator(
            source_id=self.source_id,
            version=self.version,
            locator=f"rag://{self.source_id}@{self.version}/{clean_path}",
        )


class DocumentManifest(RagModel):
    """Authorized static document set for one store/product/optional variant."""

    manifest_id: NonEmptyString
    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    document_version: NonEmptyString
    sources: tuple[DocumentSource, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest_sources(self) -> "DocumentManifest":
        source_ids: set[str] = set()
        for source in self.sources:
            if source.authorization_state is not AuthorizationState.AUTHORIZED:
                raise ValueError("manifest sources must be authorized")
            if source.store_id != self.store_id or source.product_id != self.product_id:
                raise ValueError("manifest source scope must match manifest scope")
            if source.variant_id != self.variant_id:
                raise ValueError("manifest source variant scope must match")
            if source.version != self.document_version:
                raise ValueError("manifest source version must match document_version")
            if source.source_id in source_ids:
                raise ValueError("manifest source_id values must be unique")
            source_ids.add(source.source_id)
        return self

    def source_by_id(self, source_id: str) -> DocumentSource | None:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        return None


class DocumentChunk(RagModel):
    """One ordered, replayable chunk derived from an authorized source."""

    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    source_id: NonEmptyString
    source_type: DocumentSourceType
    version: NonEmptyString
    chunk_id: NonEmptyString
    order: int = Field(ge=0)
    locator: SourceLocator
    heading_path: tuple[NonEmptyString, ...]
    text: NonEmptyString
    metadata: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_chunk_locator(self) -> "DocumentChunk":
        if self.locator.source_id != self.source_id:
            raise ValueError("chunk locator source_id must match chunk source_id")
        if self.locator.version != self.version:
            raise ValueError("chunk locator version must match chunk version")
        return self


def build_authorized_manifest(
    *,
    manifest_id: str,
    store_id: str,
    product_id: str,
    variant_id: str | None = None,
    document_version: str,
    sources: tuple[DocumentSource, ...],
) -> DocumentManifest:
    """Create a manifest while enforcing the Slice 5 authorized-source gate."""
    return DocumentManifest(
        manifest_id=manifest_id,
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        document_version=document_version,
        sources=sources,
    )


def chunk_manifest(manifest: DocumentManifest) -> tuple[DocumentChunk, ...]:
    """Chunk all manifest sources in deterministic source order."""
    chunks: list[DocumentChunk] = []
    for source in manifest.sources:
        chunks.extend(chunk_document_source(source, start_order=len(chunks)))
    return tuple(chunks)


def chunk_document_source(
    source: DocumentSource, *, start_order: int = 0
) -> tuple[DocumentChunk, ...]:
    """Create stable paragraph/list/table chunks while preserving locators."""
    heading_path: list[str] = [source.title]
    chunks: list[DocumentChunk] = []
    pending: list[str] = []
    section_index = 0

    def flush() -> None:
        nonlocal section_index
        text = "\n".join(pending).strip()
        if not text:
            pending.clear()
            return
        chunk_order = start_order + len(chunks)
        chunks.append(
            DocumentChunk(
                store_id=source.store_id,
                product_id=source.product_id,
                variant_id=source.variant_id,
                source_id=source.source_id,
                source_type=source.source_type,
                version=source.version,
                chunk_id=f"{source.source_id}:c{section_index:03d}",
                order=chunk_order,
                locator=source.locator(f"chunk/{section_index:03d}"),
                heading_path=tuple(heading_path),
                text=text,
                metadata={
                    **source.metadata,
                    "source_type": source.source_type.value,
                    "document_version": source.version,
                },
            )
        )
        section_index += 1
        pending.clear()

    for raw_line in source.text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip()
            if heading:
                heading_path[:] = [source.title, heading]
            continue
        pending.append(line)
    flush()
    return tuple(chunks)
