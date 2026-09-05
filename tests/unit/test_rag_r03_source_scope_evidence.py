"""RAG-R03 source-scope and manifest provenance coverage."""

import pytest

from backend.common import ObjectScope
from backend.evidence import RagClaim, RagFallbackReason, gate_retrieval_evidence
from backend.rag import (
    DocumentChunk,
    DocumentSourceType,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStrategy,
    SourceLocator,
)

pytestmark = pytest.mark.unit

MANIFEST_IDENTITY = "rag-corrected-chunk-baseline-v0.1:v0.1:" + ("1" * 64)


def test_product_shared_evidence_keeps_null_variant_for_variant_target() -> None:
    result = _result(
        target=ObjectScope(
            store_id="store-a", product_id="product-a", variant_id="variant-a"
        ),
        chunk=_chunk(variant_id=None),
    )
    claim = _claim(result)

    gate = gate_retrieval_evidence(result, claims=(claim,))

    assert gate.accepted_claim_ids == ("claim-a",)
    assert gate.retrieval.evidence[0].variant_id is None


def test_variant_specific_evidence_keeps_exact_source_variant() -> None:
    result = _result(
        target=ObjectScope(
            store_id="store-a", product_id="product-a", variant_id="variant-a"
        ),
        chunk=_chunk(variant_id="variant-a"),
    )
    claim = _claim(result)

    gate = gate_retrieval_evidence(result, claims=(claim,))

    assert gate.accepted_claim_ids == ("claim-a",)
    assert gate.retrieval.evidence[0].variant_id == "variant-a"


@pytest.mark.parametrize(
    ("product_id", "variant_id"),
    [
        ("product-a", "variant-b"),
        ("foreign-product", "variant-a"),
    ],
)
def test_foreign_source_scope_is_rejected_without_mutating_target(
    product_id: str,
    variant_id: str,
) -> None:
    chunk = _chunk(product_id=product_id, variant_id=variant_id)
    result = _result(
        target=ObjectScope(
            store_id="store-a", product_id="product-a", variant_id="variant-a"
        ),
        chunk=chunk,
    )
    claim = _claim(result)

    gate = gate_retrieval_evidence(result, claims=(claim,))

    assert gate.accepted_claim_ids == ()
    assert gate.fallbacks[0].reason is RagFallbackReason.SCOPE_MISMATCH
    assert gate.retrieval.request.turn_target.variant_id == "variant-a"
    assert gate.retrieval.evidence[0].variant_id == chunk.variant_id


def test_product_request_rejects_variant_specific_source() -> None:
    result = _result(
        target=ObjectScope(store_id="store-a", product_id="product-a"),
        chunk=_chunk(variant_id="variant-a"),
    )

    gate = gate_retrieval_evidence(result, claims=(_claim(result),))

    assert gate.accepted_claim_ids == ()
    assert gate.fallbacks[0].reason is RagFallbackReason.SCOPE_MISMATCH


def test_manifest_identity_is_checked_separately_from_source_version() -> None:
    result = _result(
        target=ObjectScope(store_id="store-a", product_id="product-a"),
        chunk=_chunk(variant_id=None),
    )
    claim = _claim(result)
    wrong_identity = result.evidence[0].model_copy(
        update={"metadata": {"manifest_identity": "wrong-manifest"}}
    )

    gate = gate_retrieval_evidence(
        result.model_copy(update={"evidence": (wrong_identity,)}),
        claims=(claim,),
    )

    assert gate.accepted_claim_ids == ()
    assert gate.fallbacks[0].reason is RagFallbackReason.STALE_VERSION


def _result(*, target: ObjectScope, chunk: DocumentChunk) -> RetrievalResult:
    request = RetrievalRequest(turn_target=target, question="battery")
    return RetrievalResult(
        request=request,
        evidence=(chunk,),
        retrieval_strategy=RetrievalStrategy.KEYWORD_OVERLAP,
        index_version=MANIFEST_IDENTITY,
        filtered_out_count=0,
    )


def _claim(result: RetrievalResult) -> RagClaim:
    return RagClaim(
        claim_id="claim-a",
        scope=result.request.turn_target,
        field="package_list",
        text="battery safety",
        locator=result.evidence[0].locator.locator,
    )


def _chunk(
    *,
    product_id: str = "product-a",
    variant_id: str | None,
) -> DocumentChunk:
    source_version = "source-v1"
    locator = f"rag://source-a@{source_version}/page/1#ord=0-1"
    return DocumentChunk(
        store_id="store-a",
        product_id=product_id,
        variant_id=variant_id,
        source_id="source-a",
        source_type=DocumentSourceType.MANUAL,
        version=source_version,
        chunk_id="chunk-a",
        order=0,
        locator=SourceLocator(
            source_id="source-a",
            version=source_version,
            locator=locator,
        ),
        heading_path=("manual",),
        text="battery safety",
        metadata={"manifest_identity": MANIFEST_IDENTITY},
    )
