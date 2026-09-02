"""S05-T06 integration coverage for single-target Product RAG answers."""

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
    TraceEventType,
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

pytestmark = pytest.mark.integration

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
        conversation=ConversationRef(conversation_id="s05-flow", message_id=question),
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


def _service() -> tuple[ProductRagApplicationService, InMemoryTraceSink]:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    trace = InMemoryTraceSink()
    return (
        ProductRagApplicationService(
            loop=BoundedProductRagLoop(
                retriever=InMemoryProductRetriever(
                    chunk_manifest(manifest), index_version=manifest.document_version
                ),
                clock_ms=lambda: 0,
            ),
            interpreter=ProductRagQuestionInterpreter(),
            trace_sink=trace,
            correlation_id_factory=lambda: "s05-flow-trace",
            clock=lambda: _NOW,
        ),
        trace,
    )


@pytest.mark.parametrize(
    ("question", "source_id"),
    [
        ("Which beginner flight modes are described?", "drone-travel-faq"),
        ("How many batteries are in the package?", "drone-travel-package-list"),
        ("What should I check before takeoff?", "drone-travel-manual"),
        ("Is care coverage available?", "drone-travel-policy"),
    ],
)
def test_authorized_static_document_questions_keep_resolved_target(
    question: str, source_id: str
) -> None:
    service, trace = _service()
    payload = service.answer_resolved(_request(question), _resolution(_scope())).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope == _scope()
    assert source_id in payload.evidence[0].field_locator
    assert {event.correlation_id for event in trace.events} == {"s05-flow-trace"}
    assert TraceEventType.SHOPIFY_READ_CALLED not in {
        event.event_type for event in trace.events
    }


def test_missing_document_scope_returns_no_claim_or_cross_product_evidence() -> None:
    service, _ = _service()
    payload = service.answer_resolved(
        _request("How many batteries are in the package?"),
        _resolution(_scope("drone-cinema")),
    ).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.resolved_scope == _scope("drone-cinema")
    assert payload.claims == payload.evidence == payload.bindings == []
