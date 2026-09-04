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
from backend.rag.locator_binding import (
    LocatorBinding,
    LocatorBindingRejectionReason,
    LocatorBindingResult,
    LocatorBindingSource,
    Mavic3ScopeOverlay,
    OverlayDecision,
    bind_locator_record,
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
from backend.rag.offline_retrieval import (
    CORPUS_NOT_INDEXED,
    DEFAULT_MAX_SCOPED_CANDIDATES,
    NO_SCOPED_MATCH,
    SCOPED_CANDIDATE_LIMIT,
    OfflineLocatorRecord,
    OfflineLocatorRetrievalResult,
    OfflineMetadataLocatorRetriever,
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
    "CORPUS_NOT_INDEXED",
    "DEFAULT_CORPUS_ROOT",
    "DEFAULT_MAX_SCOPED_CANDIDATES",
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
    "LocatorBinding",
    "LocatorBindingRejectionReason",
    "LocatorBindingResult",
    "LocatorBindingSource",
    "Mavic3ScopeOverlay",
    "NO_SCOPED_MATCH",
    "OfflineLocatorRecord",
    "OfflineLocatorRetrievalResult",
    "OfflineMetadataLocatorRetriever",
    "OverlayDecision",
    "RetrievalRequest",
    "RetrievalEvidenceBundle",
    "RetrievalResult",
    "RetrievalResultAdapter",
    "RetrievalStrategy",
    "SCOPED_CANDIDATE_LIMIT",
    "adapt_retrieval_result",
    "bind_locator_record",
]
