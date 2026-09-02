"""S05-T06 contract tests for Product RAG AnswerEnvelope composition."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.agent import BoundedProductRagLoop
from backend.application import (
    InMemoryTraceSink,
    ProductRagApplicationService,
    ProductRagQuestionInterpreter,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    ConversationRef,
    EnvelopeOutcome,
    ObjectScope,
    PageContext,
    TurnRequest,
)
from backend.conversation import (
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)
from backend.rag import DocumentManifest, InMemoryProductRetriever, chunk_manifest

pytestmark = pytest.mark.contract

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)
_NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _scope(product_id: str = "drone-travel") -> ObjectScope:
    return ObjectScope(store_id="store-s02-alpha", product_id=product_id)


def _request(question: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-s02-alpha",
        conversation=ConversationRef(
            conversation_id="s05-contract", message_id=question
        ),
        user_text=question,
        locale="en-US",
        page_context=PageContext(product_id="drone-cinema"),
    )


def _resolution(scope: ObjectScope) -> TargetResolution:
    return TargetResolution(
        turn_target=TurnTarget(kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=ContextAction.KEEP,
    )


def _service() -> ProductRagApplicationService:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    return ProductRagApplicationService(
        loop=BoundedProductRagLoop(
            retriever=InMemoryProductRetriever(
                chunk_manifest(manifest), index_version=manifest.document_version
            ),
            clock_ms=lambda: 0,
        ),
        interpreter=ProductRagQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "s05-contract-trace",
        clock=lambda: _NOW,
    )


def test_static_document_answer_round_trips_and_binds_one_target() -> None:
    payload = (
        _service()
        .answer_resolved(
            _request("How many batteries are in the package?"), _resolution(_scope())
        )
        .root
    )

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope == _scope()
    assert payload.evidence[0].field_locator.startswith("rag://drone-travel-package")
    assert payload.evidence[0].store_id == payload.resolved_scope.store_id
    assert payload.evidence[0].product_id == payload.resolved_scope.product_id
    assert payload.bindings[0].claim_id == payload.claims[0].claim_id
    assert AnswerEnvelope.model_validate(payload.to_wire()).root == payload


def test_dynamic_question_is_publicly_safe_fallback_without_document_claims() -> None:
    payload = (
        _service()
        .answer_resolved(_request("What is the current price?"), _resolution(_scope()))
        .root
    )

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.claims == []
    assert payload.evidence == []
    assert payload.bindings == []
    assert "实时商店数据" in payload.text
