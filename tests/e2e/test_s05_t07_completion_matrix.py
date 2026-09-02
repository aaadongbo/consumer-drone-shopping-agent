"""Slice 5 completion matrix for scoped Product RAG safety boundaries."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.agent import BoundedProductRagLoop, RagStopReason
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
from backend.evidence import RagClaim, RagFallbackReason, gate_retrieval_evidence
from backend.rag import (
    DocumentManifest,
    InMemoryProductRetriever,
    RetrievalRequest,
    chunk_manifest,
)

pytestmark = pytest.mark.e2e

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)
_NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _manifest() -> DocumentManifest:
    return DocumentManifest.model_validate_json(_FIXTURE.read_text(encoding="utf-8"))


def _scope(product_id: str = "drone-travel") -> ObjectScope:
    return ObjectScope(store_id="store-s02-alpha", product_id=product_id)


def _resolution(scope: ObjectScope) -> TargetResolution:
    return TargetResolution(
        turn_target=TurnTarget(kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=ContextAction.KEEP,
    )


def _request(question: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-s02-alpha",
        conversation=ConversationRef(conversation_id="s05-matrix", message_id=question),
        user_text=question,
        locale="en-US",
        page_context=PageContext(product_id="drone-cinema"),
    )


def _service(
    manifest: DocumentManifest | None = None,
) -> tuple[ProductRagApplicationService, InMemoryTraceSink]:
    fixture = manifest or _manifest()
    trace = InMemoryTraceSink()
    return (
        ProductRagApplicationService(
            loop=BoundedProductRagLoop(
                retriever=InMemoryProductRetriever(
                    chunk_manifest(fixture), index_version=fixture.document_version
                ),
                clock_ms=lambda: 0,
            ),
            interpreter=ProductRagQuestionInterpreter(),
            trace_sink=trace,
            correlation_id_factory=lambda: "s05-matrix-trace",
            clock=lambda: _NOW,
        ),
        trace,
    )


def _claim(result, *, text: str = "Travel Pack includes three batteries.") -> RagClaim:
    return RagClaim(
        claim_id="package-batteries",
        scope=result.request.turn_target,
        field="package_list",
        text=text,
        locator="rag://drone-travel-package-list@docs-2026-09-01/chunk/000",
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
def test_matrix_static_sources_answer_only_for_the_exact_turn_target(
    question: str, source_id: str
) -> None:
    service, _ = _service()
    payload = service.answer_resolved(_request(question), _resolution(_scope())).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope == _scope()
    assert source_id in payload.evidence[0].field_locator


def test_matrix_dynamic_question_is_a_claim_free_real_time_handoff() -> None:
    service, _ = _service()
    payload = service.answer_resolved(
        _request("What is the current inventory?"), _resolution(_scope())
    ).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.claims == payload.evidence == payload.bindings == []
    assert "实时商店数据" in payload.text


def test_matrix_foreign_document_injection_is_rejected() -> None:
    manifest = _manifest()
    result = InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    ).retrieve(
        RetrievalRequest(
            turn_target=_scope(), question="How many batteries are in the package?"
        )
    )
    injected = result.model_copy(
        update={
            "evidence": (
                result.evidence[0].model_copy(update={"product_id": "foreign"}),
            )
        }
    )

    gate = gate_retrieval_evidence(injected, claims=(_claim(result),))

    assert gate.fallbacks[0].reason is RagFallbackReason.SCOPE_MISMATCH


def test_matrix_second_round_is_the_last_allowed_corrective_read() -> None:
    manifest = _manifest()
    request = RetrievalRequest(turn_target=_scope(), question="What comes with it?")
    claim = RagClaim(
        claim_id="unsupported-package",
        scope=request.turn_target,
        field="package_list",
        text="Travel Pack includes five batteries.",
        locator="rag://drone-travel-package-list@docs-2026-09-01/chunk/000",
    )
    result = BoundedProductRagLoop(
        retriever=InMemoryProductRetriever(
            chunk_manifest(manifest), index_version=manifest.document_version
        ),
        clock_ms=lambda: 0,
    ).run(request=request, claim=claim)

    assert result.stop_reason is RagStopReason.ACTION_ROUND_LIMIT
    assert len(result.traces) == 2
    assert result.evidence_gate is not None
    assert result.evidence_gate.accepted_claim_ids == ()


def test_matrix_conflicting_document_content_falls_back() -> None:
    manifest = _manifest()
    result = InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    ).retrieve(
        RetrievalRequest(
            turn_target=_scope(), question="How many batteries are in the package?"
        )
    )
    conflict = result.evidence[0].model_copy(
        update={"text": "Travel Pack includes two batteries."}
    )
    gate = gate_retrieval_evidence(
        result.model_copy(update={"evidence": (result.evidence[0], conflict)}),
        claims=(_claim(result),),
    )

    assert gate.fallbacks[0].reason is RagFallbackReason.CONFLICTING_EVIDENCE


def test_matrix_unauthorized_manifest_source_cannot_enter_retrieval() -> None:
    manifest = _manifest()
    payload = manifest.to_wire()
    payload["sources"][0]["authorization_state"] = "UNAUTHORIZED"

    with pytest.raises(ValidationError, match="authorized"):
        DocumentManifest.model_validate(payload)


def test_matrix_derived_evidence_request_is_deferred_without_execution() -> None:
    service, trace = _service()
    payload = service.answer_resolved(
        _request("Please recompute derived evidence."), _resolution(_scope())
    ).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.claims == payload.evidence == payload.bindings == []
    assert all(event.summary.operation is None for event in trace.events)


def test_matrix_secret_like_source_metadata_never_enters_output_or_trace() -> None:
    manifest = _manifest()
    payload = manifest.to_wire()
    payload["sources"][0]["metadata"] = {"api_key": "super-secret-value"}
    service, trace = _service(DocumentManifest.model_validate(payload))
    answer = service.answer_resolved(
        _request("Which beginner flight modes are described?"), _resolution(_scope())
    )

    serialized = answer.to_wire_json() + "".join(
        event.to_wire_json() for event in trace.events
    )
    assert "super-secret-value" not in serialized
