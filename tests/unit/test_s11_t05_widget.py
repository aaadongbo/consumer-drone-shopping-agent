"""S11-T05 unit checks for the embeddable storefront widget."""

from datetime import UTC, datetime

import pytest

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
    FreshnessDisclosure,
    ProductCard,
    StandardFallback,
)
from storefront import (
    WidgetEmbedConfig,
    WidgetStatus,
    build_storefront_turn_view,
    widget_state_from_turn_view,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _config() -> WidgetEmbedConfig:
    return WidgetEmbedConfig(
        current_origin="https://beta-store.example",
        allowed_origins=("https://beta-store.example",),
        store_id="store-drone-cn",
        product_id="drone-mini",
        variant_id="mini-standard",
    )


def test_embed_config_requires_exact_allowlisted_origin_and_conversation_api() -> None:
    config = _config()

    assert config.backend_endpoint == "/v1/conversation/turn"
    assert config.page_context.product_id == "drone-mini"
    assert config.page_context.variant_id == "mini-standard"

    with pytest.raises(ValueError, match="wildcard"):
        WidgetEmbedConfig(
            current_origin="https://beta-store.example",
            allowed_origins=("https://*.example",),
            store_id="store-drone-cn",
            product_id="drone-mini",
        )
    with pytest.raises(ValueError, match="explicitly allowlisted"):
        WidgetEmbedConfig(
            current_origin="https://attacker.example",
            allowed_origins=("https://beta-store.example",),
            store_id="store-drone-cn",
            product_id="drone-mini",
        )
    with pytest.raises(ValueError, match="Conversation API"):
        WidgetEmbedConfig(
            current_origin="https://beta-store.example",
            allowed_origins=("https://beta-store.example",),
            backend_endpoint="/admin/products",
            store_id="store-drone-cn",
            product_id="drone-mini",
        )


def test_final_answer_state_renders_target_evidence_and_freshness() -> None:
    scope = _config().scope
    fact = AttributeValue(
        status=AttributeStatus.KNOWN,
        value="249 g",
        source_ref="controlled://static/weight",
    )
    envelope = AnswerEnvelope(
        root=AnswerPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.ANSWER,
            conversation=ConversationRef(
                conversation_id="conversation-widget",
                message_id="message-widget",
            ),
            trace_correlation_id="correlation-widget-answer",
            resolved_scope=scope,
            text="Mini is listed at 249 g.",
            claims=[Claim(claim_id="claim-weight", field="weight", fact=fact)],
            product_card=ProductCard(
                store_id=scope.store_id,
                product_id=scope.product_id,
                variant_id=scope.variant_id,
                display_title="DJI Mini Standard",
            ),
            evidence=[
                Evidence(
                    evidence_id="evidence-weight",
                    type=EvidenceType.TOOL,
                    store_id=scope.store_id,
                    product_id=scope.product_id,
                    variant_id=scope.variant_id,
                    field_locator="variant_attributes.weight",
                    fact=fact,
                    source="controlled://shopify",
                    observed_at=NOW,
                )
            ],
            bindings=[
                ClaimEvidenceBinding(
                    claim_id="claim-weight",
                    evidence_ids=["evidence-weight"],
                )
            ],
            freshness=FreshnessDisclosure(
                observed_at=NOW,
                source="controlled://shopify",
            ),
        )
    )

    state = widget_state_from_turn_view(build_storefront_turn_view(envelope))

    assert state.status is WidgetStatus.ANSWER
    assert state.target is not None
    assert state.target.title == "DJI Mini Standard"
    assert state.message == "Mini is listed at 249 g."
    assert len(state.evidence) == 1
    assert state.evidence[0].scope == scope
    assert state.evidence[0].source == "controlled://shopify"
    assert state.freshness is not None
    assert state.retryable is False


def test_fallback_state_exposes_safe_action_and_retry_flag_only() -> None:
    scope = _config().scope
    message = "I could not confirm that from the approved data."
    envelope = AnswerEnvelope(
        root=FallbackPayload(
            schema_version=SCHEMA_VERSION,
            outcome=EnvelopeOutcome.FALLBACK,
            conversation=ConversationRef(
                conversation_id="conversation-widget",
                message_id="message-widget",
            ),
            trace_correlation_id="correlation-widget-fallback",
            resolved_scope=scope,
            text=message,
            fallback=StandardFallback(
                reason_code=FallbackReasonCode.TOOL_TIMEOUT,
                message=message,
                retryable=True,
                next_actions=["Retry"],
                resolved_scope=scope,
            ),
        )
    )

    state = widget_state_from_turn_view(build_storefront_turn_view(envelope))

    assert state.status is WidgetStatus.FALLBACK
    assert state.fallback is not None
    assert state.fallback.reason_code is FallbackReasonCode.TOOL_TIMEOUT
    assert state.retryable is True
    assert state.evidence == ()
