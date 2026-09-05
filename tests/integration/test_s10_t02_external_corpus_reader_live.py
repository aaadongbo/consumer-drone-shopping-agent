"""S10-T02 read-only integration coverage for the approved external corpus."""

from pathlib import Path
from shutil import which

import pytest

from backend.rag import (
    ControlledRetrievalRequest,
    ExternalCorpusReader,
    ExternalCorpusStopReason,
)

pytestmark = pytest.mark.integration

CORPUS_ROOT = Path(
    "/Users/russeell/Documents/Data-Staging/consumer-drone-agent"
    "/outputs/rag-corpus-20260902-v0.1"
)
CHUNK_MANIFEST_PATH = Path(
    "/Users/russeell/Documents/Data-Staging/consumer-drone-agent"
    "/outputs/rag-corrected-chunk-baseline-20260905-v0.1"
    "/corrected-chunk-baseline.manifest.json"
)


def test_approved_external_pdf_region_matches_corrected_manifest() -> None:
    if not CORPUS_ROOT.exists() or not CHUNK_MANIFEST_PATH.exists():
        pytest.skip("approved external corpus metadata is not present")
    if which("pdftotext") is None:
        pytest.skip("pdftotext is not available for read-only source-region smoke")

    result = ExternalCorpusReader(corpus_root=CORPUS_ROOT).retrieve(
        chunk_manifest_path=CHUNK_MANIFEST_PATH,
        request=ControlledRetrievalRequest(
            store_id="bys-user-store-578412-7a11gk0u.myshopify.com",
            product_id="DJI Air 3",
            query="下载调参软件",
            field_hint="下载调参软件",
        ),
    )

    assert result.stop_reason is ExternalCorpusStopReason.SOURCE_REGION_ACCEPTED
    assert result.chunks
    assert all(chunk.product_id == "DJI Air 3" for chunk in result.chunks)
    assert result.safe_metadata()["persisted_to_repository"] is False
