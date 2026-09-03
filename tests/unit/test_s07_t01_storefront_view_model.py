"""S07-T01 unit checks for storefront-local view-model derivation."""

from datetime import UTC, datetime

import pytest

from backend.api import ConversationTransportError
from backend.common import (
    SCHEMA_VERSION,
    AnswerEnvelope,
    AnswerPayload,
    AttributeStatus,
    AttributeValue,
    Claim,
    ClaimEvidenceBinding,
    ConversationRef,
    EnvelopeOutcome,
    Evidence,
    EvidenceType,
    FallbackPayload,
    FallbackReasonCode,
    InternalDiagnosticCode,
    ObjectScope,
    ProductCard,
    StandardFallback,
    TurnRequestValidationResponse,
)
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperator,
    ConstraintProvenance,
    NormalizedConstraint,
    PendingSwitchTrigger,
    PendingTargetSwitch,
)
from storefront import (
    RenderStatus,
    StorefrontPendingClarification,
    StorefrontUiState,
    build_storefront_turn_view,
    build_transport_rejection_view,
)
from storefront.view_model import validation_rejection_to_view

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)


def _conversation() -> ConversationRef:
    return ConversationRef(
        conversation_id="conversation-s07-t01",
        message_id="message-s07-t01",
    )


def _scope(variant_id: str | None = "mini-standard") -> ObjectScope:
    return ObjectScope(
        store_id="store-drone-cn",
        product_id="drone-mini",
        variant_id=variant_id,
    )


def _known_fact() -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=1,
        unit="battery",
        source_ref="controlled://variant/battery",
    )


def _answer_envelope() -> AnswerEnvelope:
    scope = _scope()
    fact = _known_fact()
    return AnswerEnvelope(
        root=AnswerPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.ANSWER,
            conversation=_conversation(),
            trace_correlation_id="correlation-s07-answer",
            resolved_scope=scope,
            text="这个套装有 1 块电池。",
            claims=[Claim(claim_id="claim-battery", field="battery_count", fact=fact)],
            product_card=ProductCard(
                store_id=scope.store_id,
                product_id=scope.product_id,
                variant_id=scope.variant_id,
                display_title="DJI Mini Standard Combo",
            ),
            evidence=[
                Evidence(
                    evidence_id="evidence-battery",
                    type=EvidenceType.TOOL,
                    store_id=scope.store_id,
                    product_id=scope.product_id,
                    variant_id=scope.variant_id,
                    field_locator="variant_attributes.battery_count",
                    fact=fact,
                    source="controlled://shopify",
                    observed_at=NOW,
                )
            ],
            bindings=[
                ClaimEvidenceBinding(
                    claim_id="claim-battery", evidence_ids=["evidence-battery"]
                )
            ],
        )
    )


def _fallback_envelope() -> AnswerEnvelope:
    scope = _scope()
    message = "当前授权数据无法确认该项事实。"
    return AnswerEnvelope(
        root=FallbackPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.FALLBACK,
            conversation=_conversation(),
            trace_correlation_id="correlation-s07-fallback",
            resolved_scope=scope,
            text=message,
            fallback=StandardFallback(
                reason_code=FallbackReasonCode.FACT_UNKNOWN_OR_MISSING,
                message=message,
                retryable=False,
                next_actions=["查看其他已知规格", "联系商家确认"],
                resolved_scope=scope,
            ),
        )
    )


def _constraint() -> NormalizedConstraint:
    return NormalizedConstraint(
        source_turn_id="message-s07-t01",
        field=ConstraintField.PRICE,
        operator=ConstraintOperator.LTE,
        value=5000,
        unit="CNY",
        hardness=ConstraintHardness.HARD,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def test_answer_envelope_maps_one_to_one_with_target_and_constraints() -> None:
    pending_switch = PendingTargetSwitch(
        target=_scope(None),
        created_by_message_id="message-switch",
        created_at_revision=3,
        expected_revision=3,
        trigger=PendingSwitchTrigger.USER_SWITCH_REQUEST,
    )
    ui_state = StorefrontUiState(
        active_constraints=(_constraint(),),
        pending_clarification=StorefrontPendingClarification(
            prompt="预算上限是多少？",
            source_message_id="message-clarify",
            consecutive_count=1,
        ),
        pending_target_switch=pending_switch,
        submitting=True,
    )

    view = build_storefront_turn_view(_answer_envelope(), ui_state=ui_state)

    assert view.render_status is RenderStatus.ANSWER
    assert view.answer == _answer_envelope().root
    assert view.fallback is None
    assert view.trace_correlation_id == "correlation-s07-answer"
    assert view.target.scope == _scope()
    assert view.target.title == "DJI Mini Standard Combo"
    assert view.constraint_state.active_constraints == (_constraint(),)
    assert view.constraint_state.pending_clarification == ui_state.pending_clarification
    assert view.constraint_state.pending_target_switch == pending_switch
    assert view.constraint_state.submitting is True


def test_fallback_envelope_maps_only_public_safe_fallback_fields() -> None:
    view = build_storefront_turn_view(_fallback_envelope())

    assert view.render_status is RenderStatus.FALLBACK
    assert view.answer is None
    assert view.fallback is not None
    assert view.fallback.reason_code is FallbackReasonCode.FACT_UNKNOWN_OR_MISSING
    assert view.fallback.message == "当前授权数据无法确认该项事实。"
    assert view.fallback.retryable is False
    assert view.fallback.next_actions == ("查看其他已知规格", "联系商家确认")
    assert view.fallback.resolved_scope == _scope()


def test_internal_diagnostic_values_cannot_leak_into_storefront_copy() -> None:
    scope = _scope()
    diagnostic = InternalDiagnosticCode.EVIDENCE_SCOPE_MISMATCH.value
    envelope = AnswerEnvelope(
        root=FallbackPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.FALLBACK,
            conversation=_conversation(),
            trace_correlation_id="correlation-s07-diagnostic",
            resolved_scope=scope,
            text=f"内部错误：{diagnostic}",
            fallback=StandardFallback(
                reason_code=FallbackReasonCode.INTERNAL_CONSISTENCY_ERROR,
                message=f"内部错误：{diagnostic}",
                retryable=False,
                next_actions=["联系支持"],
                resolved_scope=scope,
            ),
        )
    )

    with pytest.raises(ValueError, match="internal diagnostics"):
        build_storefront_turn_view(envelope)


def test_scope_mismatches_fail_closed_before_rendering() -> None:
    envelope = _answer_envelope()
    wrong_card_payload = envelope.root.model_copy(
        update={
            "product_card": ProductCard(
                store_id="store-drone-cn",
                product_id="other-product",
                variant_id="mini-standard",
                display_title="Wrong Product",
            )
        }
    )

    with pytest.raises(ValueError, match="product card scope"):
        build_storefront_turn_view(AnswerEnvelope(root=wrong_card_payload))


def test_transport_rejection_is_not_a_business_fallback_view() -> None:
    response = TurnRequestValidationResponse(
        schema_version=SCHEMA_VERSION,
        error_code="INVALID_TURN_REQUEST",
        message="Request validation failed.",
    )
    error = ConversationTransportError(status_code=422, response=response)

    view = build_transport_rejection_view(error)
    direct_view = validation_rejection_to_view(response)

    assert view.render_status is RenderStatus.TRANSPORT_REJECTION
    assert view.status_code == 422
    assert view.error_code == "INVALID_TURN_REQUEST"
    assert not hasattr(view, "fallback")
    assert direct_view == view
