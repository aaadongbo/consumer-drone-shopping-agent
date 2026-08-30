"""T04's single, deterministic Variant-specific application path."""

from collections.abc import Callable
from datetime import datetime

from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    AnswerPayload,
    AttributeStatus,
    Claim,
    ClaimEvidenceBinding,
    EnvelopeOutcome,
    Evidence,
    EvidenceType,
    FieldScope,
    MinimalRouteDecision,
    ObjectScope,
    RouteAction,
    RouteIntent,
    ToolStatus,
    TraceEvent,
    TraceEventType,
    TraceOperation,
    TraceResult,
    TraceSummary,
    TurnRequest,
)
from backend.shopify.port import ShopifyReadPort

_SUPPORTED_QUESTION = "这个套装有几块电池？"
_REQUESTED_FIELD = "battery_count"
_CLAIM_ID = "claim-battery-count"
_EVIDENCE_ID = "evidence-battery-count"


class _T04NonAnswer(RuntimeError):
    """Stop this deliberately narrow path without manufacturing an answer."""


class DeterministicQuestionInterpreter:
    """Recognize only T04's fixed battery-count question."""

    def interpret(self, request: TurnRequest) -> MinimalRouteDecision:
        if request.user_text != _SUPPORTED_QUESTION:
            raise _T04NonAnswer("T04 question is not supported")
        if request.page_context.variant_id is None:
            raise _T04NonAnswer("T04 requires an explicit variant")

        return MinimalRouteDecision(
            intent=RouteIntent.PRODUCT_QA,
            action=RouteAction.READ_VARIANT_FACT,
            requested_field=_REQUESTED_FIELD,
            field_scope=FieldScope.VARIANT_SPECIFIC,
            resolved_scope=_request_scope(request),
            reason="T04 deterministic battery-count question",
        )


class InMemoryTraceSink:
    """Keep only validated, summary-only Trace Contract events in memory."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def append(self, event: TraceEvent) -> None:
        self._events.append(event)


class Slice1ApplicationService:
    """Execute only T04's fixed get_variants happy path."""

    def __init__(
        self,
        *,
        shopify: ShopifyReadPort,
        interpreter: DeterministicQuestionInterpreter,
        trace_sink: InMemoryTraceSink,
        correlation_id_factory: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        self._shopify = shopify
        self._interpreter = interpreter
        self._trace_sink = trace_sink
        self._correlation_id_factory = correlation_id_factory
        self._clock = clock

    def answer(self, request: TurnRequest) -> AnswerEnvelope:
        correlation_id = self._correlation_id_factory()
        request_scope = _request_scope(request)
        self._trace(
            correlation_id,
            TraceEventType.TURN_REQUEST_ACCEPTED,
            TraceResult.ACCEPTED,
            scope=request_scope,
        )
        if request_scope.variant_id is None:
            raise _T04NonAnswer("T04 requires an explicit variant")
        self._trace(
            correlation_id,
            TraceEventType.PAGE_CONTEXT_RESOLVED,
            TraceResult.SUCCESS,
            scope=request_scope,
        )

        decision = self._interpreter.interpret(request)
        _require_t04_route(decision, request_scope)
        self._trace(
            correlation_id,
            TraceEventType.ROUTE_DECISION,
            TraceResult.SUCCESS,
            scope=decision.resolved_scope,
        )
        self._trace(
            correlation_id,
            TraceEventType.SHOPIFY_READ_CALLED,
            TraceResult.ACCEPTED,
            scope=request_scope,
            operation=TraceOperation.GET_VARIANTS,
        )

        result = self._shopify.get_variants(
            store_id=request_scope.store_id,
            product_id=request_scope.product_id,
            variant_id=request_scope.variant_id,
        )
        self._trace(
            correlation_id,
            TraceEventType.TOOL_RESULT,
            _trace_result(result.status),
            scope=request_scope,
            operation=TraceOperation.GET_VARIANTS,
            tool_status=result.status,
        )

        if result.status is not ToolStatus.SUCCESS or result.data is None:
            raise _T04NonAnswer("Shopify read did not succeed")
        if len(result.data) != 1:
            raise _T04NonAnswer("Shopify read did not resolve exactly one variant")

        variant = result.data[0]
        if (
            variant.store_id,
            variant.product_id,
            variant.variant_id,
        ) != (
            request_scope.store_id,
            request_scope.product_id,
            request_scope.variant_id,
        ):
            raise _T04NonAnswer("ToolResult identity does not match request scope")

        fact = variant.variant_attributes.get(_REQUESTED_FIELD)
        if fact is None:
            raise _T04NonAnswer("Requested field is missing")
        if fact.status is not AttributeStatus.KNOWN:
            raise _T04NonAnswer("Requested field is not known")

        evidence = Evidence(
            evidence_id=_EVIDENCE_ID,
            type=EvidenceType.TOOL,
            store_id=variant.store_id,
            product_id=variant.product_id,
            variant_id=variant.variant_id,
            field_locator=f"variant_attributes.{_REQUESTED_FIELD}",
            fact=fact,
            source=result.source,
            observed_at=result.observed_at,
        )
        self._trace(
            correlation_id,
            TraceEventType.EVIDENCE_ACCEPTED,
            TraceResult.ACCEPTED,
            scope=request_scope,
        )

        payload = AnswerPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.ANSWER,
            conversation=request.conversation,
            trace_correlation_id=correlation_id,
            resolved_scope=request_scope,
            text=f"这个套装有 {fact.value} 块电池。",
            claims=[Claim(claim_id=_CLAIM_ID, field=_REQUESTED_FIELD, fact=fact)],
            evidence=[evidence],
            bindings=[
                ClaimEvidenceBinding(
                    claim_id=_CLAIM_ID,
                    evidence_ids=[_EVIDENCE_ID],
                )
            ],
        )
        _require_answer_integrity(payload)
        envelope = AnswerEnvelope(root=payload)
        self._trace(
            correlation_id,
            TraceEventType.ANSWER_PRODUCED,
            TraceResult.ANSWER,
            scope=request_scope,
        )
        return envelope

    def _trace(
        self,
        correlation_id: str,
        event_type: TraceEventType,
        result: TraceResult,
        *,
        scope: ObjectScope,
        operation: TraceOperation | None = None,
        tool_status: ToolStatus | None = None,
    ) -> None:
        self._trace_sink.append(
            TraceEvent(
                schema_version=SCHEMA_VERSION,
                correlation_id=correlation_id,
                event_type=event_type,
                occurred_at=self._clock(),
                summary=TraceSummary(
                    result=result,
                    scope=scope,
                    operation=operation,
                    tool_status=tool_status,
                ),
            )
        )


def _request_scope(request: TurnRequest) -> ObjectScope:
    return ObjectScope(
        store_id=request.store_id,
        product_id=request.page_context.product_id,
        variant_id=request.page_context.variant_id,
    )


def _require_t04_route(
    decision: MinimalRouteDecision, request_scope: ObjectScope
) -> None:
    if (
        decision.intent is not RouteIntent.PRODUCT_QA
        or decision.action is not RouteAction.READ_VARIANT_FACT
        or decision.requested_field != _REQUESTED_FIELD
        or decision.field_scope is not FieldScope.VARIANT_SPECIFIC
        or decision.resolved_scope != request_scope
    ):
        raise _T04NonAnswer("Route is outside the fixed T04 path")


def _require_answer_integrity(payload: AnswerPayload) -> None:
    evidence_by_id = {item.evidence_id: item for item in payload.evidence}
    bindings_by_claim: dict[str, list[ClaimEvidenceBinding]] = {}
    for binding in payload.bindings:
        bindings_by_claim.setdefault(binding.claim_id, []).append(binding)

    expected_identity = (
        payload.resolved_scope.store_id,
        payload.resolved_scope.product_id,
        payload.resolved_scope.variant_id,
    )
    for claim in payload.claims:
        claim_bindings = bindings_by_claim.get(claim.claim_id, [])
        if len(claim_bindings) != 1:
            raise _T04NonAnswer("Claim must have exactly one binding")
        evidence_ids = claim_bindings[0].evidence_ids
        if len(evidence_ids) != 1 or evidence_ids[0] not in evidence_by_id:
            raise _T04NonAnswer("Binding must identify exactly one existing evidence")
        bound_evidence = evidence_by_id[evidence_ids[0]]
        if bound_evidence.fact != claim.fact:
            raise _T04NonAnswer("Claim and Evidence facts differ")
        if (
            bound_evidence.store_id,
            bound_evidence.product_id,
            bound_evidence.variant_id,
        ) != expected_identity:
            raise _T04NonAnswer("Evidence identity differs from answer scope")


def _trace_result(status: ToolStatus) -> TraceResult:
    return {
        ToolStatus.SUCCESS: TraceResult.SUCCESS,
        ToolStatus.PARTIAL: TraceResult.PARTIAL,
        ToolStatus.ERROR: TraceResult.ERROR,
    }[status]
