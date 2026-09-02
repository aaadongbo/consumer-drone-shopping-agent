"""S05-T06 in-process end-to-end Product RAG journey."""

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

pytestmark = pytest.mark.e2e

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def test_resolved_product_question_reaches_bound_answer_without_shopify() -> None:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    trace = InMemoryTraceSink()
    service = ProductRagApplicationService(
        loop=BoundedProductRagLoop(
            retriever=InMemoryProductRetriever(
                chunk_manifest(manifest), index_version=manifest.document_version
            ),
            clock_ms=lambda: 0,
        ),
        interpreter=ProductRagQuestionInterpreter(),
        trace_sink=trace,
        correlation_id_factory=lambda: "s05-e2e-trace",
        clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
    )
    scope = ObjectScope(store_id="store-s02-alpha", product_id="drone-travel")
    request = TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=scope.store_id,
        conversation=ConversationRef(conversation_id="s05-e2e", message_id="m1"),
        user_text="What should I check before takeoff?",
        locale="en-US",
        page_context=PageContext(product_id="drone-cinema"),
    )
    resolution = TargetResolution(
        turn_target=TurnTarget(kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=ContextAction.KEEP,
    )

    payload = service.answer_resolved(request, resolution).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope == scope
    assert payload.evidence[0].product_id == "drone-travel"
    assert payload.evidence[0].field_locator.endswith(
        "manual@docs-2026-09-01/chunk/000"
    )
    assert len(trace.events) == 4
