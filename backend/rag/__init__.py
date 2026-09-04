"""Internal Product RAG boundaries for authorized product documents."""

from backend.rag.adapters import (
    RetrievalEvidenceBundle,
    RetrievalResultAdapter,
    adapt_retrieval_result,
)
from backend.rag.corpus_readiness import (
    DEFAULT_CORPUS_ROOT,
    CorpusFileValidation,
    CorpusReadinessReport,
    CorpusReadinessStopReason,
    build_corpus_readiness_report,
)
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
    "CorpusFileValidation",
    "CorpusReadinessReport",
    "CorpusReadinessStopReason",
    "DEFAULT_CORPUS_ROOT",
    "DocumentChunk",
    "DocumentManifest",
    "DocumentSource",
    "DocumentSourceType",
    "SourceLocator",
    "build_authorized_manifest",
    "build_corpus_readiness_report",
    "chunk_document_source",
    "chunk_manifest",
    "InMemoryProductRetriever",
    "RetrievalRequest",
    "RetrievalEvidenceBundle",
    "RetrievalResult",
    "RetrievalResultAdapter",
    "RetrievalStrategy",
    "adapt_retrieval_result",
]
