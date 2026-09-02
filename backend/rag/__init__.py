"""Internal Product RAG boundaries for authorized product documents."""

from backend.rag.manifest import (
    AuthorizationState,
    DocumentChunk,
    DocumentManifest,
    DocumentSource,
    DocumentSourceType,
    SourceLocator,
    build_authorized_manifest,
    chunk_document_source,
    chunk_manifest,
)
from backend.rag.retrieval import (
    InMemoryProductRetriever,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStrategy,
)

__all__ = [
    "AuthorizationState",
    "DocumentChunk",
    "DocumentManifest",
    "DocumentSource",
    "DocumentSourceType",
    "SourceLocator",
    "build_authorized_manifest",
    "chunk_document_source",
    "chunk_manifest",
    "InMemoryProductRetriever",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalStrategy",
]
