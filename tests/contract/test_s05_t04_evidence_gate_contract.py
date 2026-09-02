"""S05-T04 contract coverage for internal RAG Evidence Quality models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.common import ObjectScope
from backend.evidence import (
    EvidenceQuality,
    EvidenceQualityVerdict,
    RagClaim,
    RagFallbackReason,
    gate_retrieval_evidence,
)
from backend.rag import (
    DocumentManifest,
    InMemoryProductRetriever,
    RetrievalEvidenceBundle,
    RetrievalRequest,
    chunk_manifest,
)

pytestmark = pytest.mark.contract

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


def _claim(
    *,
    field: str = "package_list",
    text: str = "Travel Pack includes three batteries.",
):
    result = _result()
    return RagClaim(
        claim_id="package-batteries",
        scope=result.request.turn_target,
        field=field,
        text=text,
        locator=result.evidence[0].locator.locator,
    )


def test_retrieval_adapter_round_trips_without_losing_scope_or_version() -> None:
    result = _result()
    bundle = RetrievalEvidenceBundle.from_result(result)

    assert bundle.to_result() == result
    assert RetrievalEvidenceBundle.model_validate(bundle.to_wire()) == bundle


def test_accepted_quality_requires_all_gate_signals_and_a_locator() -> None:
    with pytest.raises(ValidationError, match="accepted evidence"):
        EvidenceQuality(
            claim_id="missing-coverage",
            verdict=EvidenceQualityVerdict.ACCEPTED,
            scope_match=True,
            locator_present=True,
            version_match=True,
            claim_covered=False,
            conflict=False,
            evidence_locators=("rag://source@v/chunk/000",),
        )


@pytest.mark.parametrize(
    ("field", "expected_reason"),
    [("price", RagFallbackReason.DYNAMIC_FACT_REQUIRED)],
)
def test_dynamic_commerce_claim_is_never_document_accepted(
    field: str, expected_reason: RagFallbackReason
) -> None:
    gate = gate_retrieval_evidence(_result(), claims=(_claim(field=field),))

    assert gate.accepted_claim_ids == ()
    assert gate.fallbacks[0].reason is expected_reason


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        (
            lambda chunk: chunk.model_validate(
                {
                    **chunk.to_wire(),
                    "version": "docs-2025-01-01",
                    "locator": {
                        **chunk.locator.to_wire(),
                        "version": "docs-2025-01-01",
                        "locator": chunk.locator.locator.replace(
                            "docs-2026-09-01", "docs-2025-01-01"
                        ),
                    },
                }
            ),
            RagFallbackReason.STALE_VERSION,
        ),
        (
            lambda chunk: chunk.model_copy(
                update={"text": "Travel Pack includes two batteries."}
            ),
            RagFallbackReason.CONFLICTING_EVIDENCE,
        ),
    ],
)
def test_stale_or_conflicting_locator_cannot_support_claim(
    mutation, expected_reason: RagFallbackReason
) -> None:
    result = _result()
    original = result.evidence[0]
    mutated = result.model_copy(update={"evidence": (original, mutation(original))})
    claim = _claim()
    if expected_reason is RagFallbackReason.STALE_VERSION:
        claim = claim.model_copy(
            update={"locator": mutated.evidence[1].locator.locator}
        )

    gate = gate_retrieval_evidence(mutated, claims=(claim,))

    assert gate.accepted_claim_ids == ()
    assert gate.fallbacks[0].reason is expected_reason
