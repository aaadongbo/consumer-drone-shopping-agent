"""S03-T05 resolved single-object journeys through the existing fact flow."""

from collections import Counter
from datetime import UTC, datetime

import pytest

from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
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
from backend.shopify.fixture import DeterministicShopifyFixture

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)


def target(product_id: str, variant_id: str | None = None) -> TargetResolution:
    scope = ObjectScope(
        store_id="store-drone-cn", product_id=product_id, variant_id=variant_id
    )
    return TargetResolution(
        turn_target=TurnTarget(kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=ContextAction.KEEP,
    )


def request(page_product: str = "drone-mini") -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(conversation_id="t05", message_id="m1"),
        user_text="这款无人机的制造商是谁？",
        locale="zh-CN",
        page_context=PageContext(product_id=page_product),
    )


def system() -> tuple[Slice1ApplicationService, DeterministicShopifyFixture]:
    fixture = DeterministicShopifyFixture(clock=lambda: NOW)
    return (
        Slice1ApplicationService(
            shopify=fixture,
            interpreter=DeterministicQuestionInterpreter(),
            trace_sink=InMemoryTraceSink(),
            correlation_id_factory=lambda: "s03-t05",
            clock=lambda: NOW,
        ),
        fixture,
    )


@pytest.mark.parametrize(
    ("page_product", "resolved_product", "expected_manufacturer"),
    [
        ("drone-mini", "drone-mini", "Aero Labs"),
        ("drone-mini", "drone-cine", "Aero Labs"),
        ("drone-cine", "drone-mini", "Aero Labs"),
    ],
    ids=["page-default", "explicit-temporary-override", "confirmed-switch"],
)
def test_resolved_target_is_the_only_fact_read_identity(
    page_product: str, resolved_product: str, expected_manufacturer: str
) -> None:
    service, fixture = system()

    payload = AnswerEnvelope.model_validate_json(
        service.answer_resolved(
            request(page_product), target(resolved_product)
        ).to_wire_json()
    ).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.resolved_scope.product_id == resolved_product
    assert payload.claims[0].fact.value == expected_manufacturer
    assert payload.evidence[0].product_id == resolved_product
    assert payload.bindings[0].claim_id == payload.claims[0].claim_id
    assert [entry.product_id for entry in fixture.call_ledger] == [resolved_product]
    assert fixture.write_call_count == 0


def test_invalid_target_fails_closed_without_a_page_context_read() -> None:
    service, fixture = system()
    invalid = TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.NEEDS_CLARIFICATION,
            clarification_reason="ambiguous",
        ),
        context_action=ContextAction.KEEP,
    )

    payload = service.answer_resolved(request(), invalid).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR
    assert Counter(entry.operation for entry in fixture.call_ledger) == Counter()
    assert fixture.write_call_count == 0
