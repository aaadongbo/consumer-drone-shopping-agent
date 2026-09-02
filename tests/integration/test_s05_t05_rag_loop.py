"""S05-T05 integration tests for Product RAG action trace and budgets."""

from pathlib import Path

import pytest

from backend.agent import BoundedProductRagLoop, ProductRagBudget, RagStopReason
from backend.common import ObjectScope
from backend.evidence import RagClaim
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


def _request() -> RetrievalRequest:
    return RetrievalRequest(
        turn_target=ObjectScope(store_id="store-s02-alpha", product_id="drone-travel"),
        question="What comes with it?",
    )


def _claim(request: RetrievalRequest) -> RagClaim:
    return RagClaim(
        claim_id="package-batteries",
        scope=request.turn_target,
        field="package_list",
        text="Travel Pack includes three batteries.",
        locator=("rag://drone-travel-package-list@docs-2026-09-01/chunk/000"),
    )


def _service(*, budget: ProductRagBudget | None = None) -> BoundedProductRagLoop:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    return BoundedProductRagLoop(
        retriever=InMemoryProductRetriever(
            chunk_manifest(manifest), index_version=manifest.document_version
        ),
        budget=budget,
        clock_ms=lambda: 0,
    )


def test_corrective_trace_replays_a_fixed_target_and_ends_with_evidence() -> None:
    request = _request()
    result = _service().run(request=request, claim=_claim(request))

    assert result.stop_reason is RagStopReason.EVIDENCE_ACCEPTED
    assert len(result.traces) == 2
    assert result.evidence_gate is not None
    assert result.evidence_gate.accepted_claim_ids == ("package-batteries",)
    assert all(
        trace.action_plan.target_scope == request.turn_target for trace in result.traces
    )
    assert result.traces[-1].budget_consumption.action_rounds == 2


def test_retrieval_token_budget_fails_closed_before_an_answer_can_be_used() -> None:
    request = _request()
    result = _service(budget=ProductRagBudget(max_retrieval_tokens=1)).run(
        request=request, claim=_claim(request)
    )

    assert result.stop_reason is RagStopReason.RETRIEVAL_TOKEN_BUDGET
    assert result.evidence_gate is not None
    assert result.evidence_gate.accepted_claim_ids == ()
