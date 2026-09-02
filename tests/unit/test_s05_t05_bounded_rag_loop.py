"""S05-T05 unit tests for the two-round Product RAG action boundary."""

from pathlib import Path

import pytest

from backend.agent import (
    BoundedProductRagLoop,
    ProductRagBudget,
    RagAction,
    RagStopReason,
)
from backend.common import ObjectScope
from backend.evidence import RagClaim
from backend.rag import (
    DocumentManifest,
    InMemoryProductRetriever,
    RetrievalRequest,
    chunk_manifest,
)

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def _retriever() -> InMemoryProductRetriever:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    return InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    )


def _request(
    question: str = "How many batteries are in the package?",
) -> RetrievalRequest:
    return RetrievalRequest(
        turn_target=ObjectScope(store_id="store-s02-alpha", product_id="drone-travel"),
        question=question,
    )


def _claim(request: RetrievalRequest, *, field: str = "package_list") -> RagClaim:
    return RagClaim(
        claim_id="package-batteries",
        scope=request.turn_target,
        field=field,
        text="Travel Pack includes three batteries.",
        locator=("rag://drone-travel-package-list@docs-2026-09-01/chunk/000"),
    )


def test_baseline_evidence_stops_after_one_scoped_read() -> None:
    request = _request()
    result = BoundedProductRagLoop(retriever=_retriever(), clock_ms=lambda: 0).run(
        request=request,
        claim=_claim(request),
    )

    assert result.stop_reason is RagStopReason.EVIDENCE_ACCEPTED
    assert len(result.traces) == 1
    assert result.traces[0].action_plan.action is RagAction.BASELINE_RETRIEVAL
    assert result.traces[0].budget_consumption.tool_calls == 1


def test_one_targeted_second_round_can_recover_missing_baseline_evidence() -> None:
    request = _request("What comes with it?")
    result = BoundedProductRagLoop(retriever=_retriever(), clock_ms=lambda: 0).run(
        request=request,
        claim=_claim(request),
    )

    assert result.stop_reason is RagStopReason.EVIDENCE_ACCEPTED
    assert [trace.action_plan.action for trace in result.traces] == [
        RagAction.BASELINE_RETRIEVAL,
        RagAction.TARGETED_RETRIEVAL,
    ]
    assert result.traces[-1].budget_consumption.tool_calls == 2
    assert all(
        trace.action_plan.target_scope == request.turn_target for trace in result.traces
    )


def test_tool_call_budget_stops_before_second_read() -> None:
    request = _request("What comes with it?")
    result = BoundedProductRagLoop(
        retriever=_retriever(),
        budget=ProductRagBudget(max_tool_calls=1),
        clock_ms=lambda: 0,
    ).run(request=request, claim=_claim(request))

    assert result.stop_reason is RagStopReason.TOOL_CALL_LIMIT
    assert len(result.traces) == 1
    assert result.traces[0].budget_consumption.tool_calls == 1


def test_action_round_budget_stops_after_baseline_without_a_second_action() -> None:
    request = _request("What comes with it?")
    result = BoundedProductRagLoop(
        retriever=_retriever(),
        budget=ProductRagBudget(max_action_rounds=1),
        clock_ms=lambda: 0,
    ).run(request=request, claim=_claim(request))

    assert result.stop_reason is RagStopReason.ACTION_ROUND_LIMIT
    assert len(result.traces) == 1


def test_turn_deadline_stops_after_the_baseline_observation() -> None:
    request = _request("What comes with it?")
    ticks = iter((0, 8000))
    result = BoundedProductRagLoop(
        retriever=_retriever(), clock_ms=lambda: next(ticks)
    ).run(request=request, claim=_claim(request))

    assert result.stop_reason is RagStopReason.TURN_DEADLINE
    assert len(result.traces) == 1


def test_dynamic_field_stops_without_a_document_correction_round() -> None:
    request = _request()
    result = BoundedProductRagLoop(retriever=_retriever(), clock_ms=lambda: 0).run(
        request=request,
        claim=_claim(request, field="price"),
    )

    assert result.stop_reason is RagStopReason.DYNAMIC_FACT_REQUIRED
    assert len(result.traces) == 1


def test_clarification_is_a_second_action_without_a_second_read() -> None:
    request = _request("What comes with it?")
    result = BoundedProductRagLoop(retriever=_retriever(), clock_ms=lambda: 0).run(
        request=request,
        claim=_claim(request),
        corrective_action=RagAction.REQUEST_CLARIFICATION,
    )

    assert result.stop_reason is RagStopReason.CLARIFICATION_REQUIRED
    assert [trace.action_plan.action for trace in result.traces] == [
        RagAction.BASELINE_RETRIEVAL,
        RagAction.REQUEST_CLARIFICATION,
    ]
    assert result.traces[-1].budget_consumption.tool_calls == 1
