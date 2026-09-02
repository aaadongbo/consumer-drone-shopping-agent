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
