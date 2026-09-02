"""S05-T04 integration coverage for retrieval-to-Evidence quality gating."""

from pathlib import Path

import pytest

from backend.common import ObjectScope
from backend.evidence import RagClaim, RagFallbackReason, gate_retrieval_evidence
from backend.rag import (
    DocumentManifest,
    InMemoryProductRetriever,
    RetrievalRequest,
    chunk_manifest,
)

pytestmark = pytest.mark.integration

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def _result():
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    return InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    ).retrieve(
        RetrievalRequest(
            turn_target=ObjectScope(
                store_id="store-s02-alpha", product_id="drone-travel"
            ),
            question="How many batteries are in the package?",
        )
    )


def _claim(result, *, text: str = "Travel Pack includes three batteries.") -> RagClaim:
    return RagClaim(
        claim_id="package-batteries",
        scope=result.request.turn_target,
        field="package_list",
        text=text,
        locator=result.evidence[0].locator.locator,
    )


def test_exact_targeted_source_excerpt_passes_evidence_gate() -> None:
    result = _result()
    gate = gate_retrieval_evidence(result, claims=(_claim(result),))

    assert gate.accepted_claim_ids == ("package-batteries",)
    assert gate.fallbacks == ()
    assert gate.quality[0].evidence_locators == (result.evidence[0].locator.locator,)


def test_foreign_product_injected_at_claim_locator_is_rejected() -> None:
    result = _result()
    foreign = result.evidence[0].model_copy(update={"product_id": "drone-cinema"})
    injected = result.model_copy(update={"evidence": (foreign,)})

    gate = gate_retrieval_evidence(injected, claims=(_claim(result),))

    assert gate.accepted_claim_ids == ()
    assert gate.fallbacks[0].reason is RagFallbackReason.SCOPE_MISMATCH


def test_unsupported_text_falls_back_instead_of_becoming_a_claim() -> None:
    result = _result()
    gate = gate_retrieval_evidence(
        result,
        claims=(_claim(result, text="Travel Pack includes five batteries."),),
    )

    assert gate.accepted_claim_ids == ()
    assert gate.fallbacks[0].reason is RagFallbackReason.EVIDENCE_MISSING
