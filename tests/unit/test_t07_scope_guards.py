"""T07 unit gates for Composer scope, binding, freshness, and trace safety."""

from datetime import UTC, datetime

import pytest

from backend.application.slice_1 import (
    _compose_answer,
    _ComposerDiagnostic,
    _safe_trace_value,
)
from backend.common import (
    SCHEMA_VERSION,
    AnswerPayload,
    AttributeStatus,
    AttributeValue,
    Claim,
    ClaimEvidenceBinding,
    ConversationRef,
    EnvelopeOutcome,
    Evidence,
    EvidenceType,
    FreshnessDisclosure,
    InternalDiagnosticCode,
    ObjectScope,
    ProductCard,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 30, 13, 0, tzinfo=UTC)


def _fact(*, observed_at: datetime | None = None) -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=2999,
        unit="CNY",
        source_ref="controlled://commerce#price",
        observed_at=observed_at,
    )


def _payload(
    *,
    evidence_scope: ObjectScope,
    evidence_locator: str = "commerce.price",
    evidence_observed_at: datetime | None = NOW,
    fact_observed_at: datetime | None = NOW,
    product_card: ObjectScope | None = None,
    with_binding: bool = True,
) -> AnswerPayload:
    scope = ObjectScope(
        store_id="store-drone-cn",
        product_id="drone-mini",
        variant_id="mini-standard",
    )
    fact = _fact(observed_at=fact_observed_at)
    evidence = Evidence(
        evidence_id="evidence-price",
        type=EvidenceType.TOOL,
        store_id=evidence_scope.store_id,
        product_id=evidence_scope.product_id,
        variant_id=evidence_scope.variant_id,
        field_locator=evidence_locator,
        fact=fact,
        source="controlled://commerce",
        observed_at=evidence_observed_at,
    )
    return AnswerPayload(
        schema_version=SCHEMA_VERSION,
        outcome=EnvelopeOutcome.ANSWER,
        conversation=ConversationRef(
            conversation_id="conversation-t07",
            message_id="message-t07",
        ),
        trace_correlation_id="correlation-t07",
        resolved_scope=scope,
        text="这款当前价格为 2999 CNY。",
        claims=[Claim(claim_id="claim-price", field="price", fact=fact)],
        product_card=(
            ProductCard(
                store_id=product_card.store_id,
                product_id=product_card.product_id,
                variant_id=product_card.variant_id,
                display_title="Aero Mini",
            )
            if product_card is not None
            else None
        ),
        evidence=[evidence],
        bindings=(
            [
                ClaimEvidenceBinding(
                    claim_id="claim-price", evidence_ids=["evidence-price"]
                )
            ]
            if with_binding
            else []
        ),
        freshness=FreshnessDisclosure(
            observed_at=NOW,
            source="controlled://commerce",
        ),
    )


@pytest.mark.parametrize(
    "evidence_scope",
    [
        ObjectScope(
            store_id="store-drone-cn",
            product_id="drone-cine",
            variant_id="cine-standard",
        ),
        ObjectScope(
            store_id="other-store",
            product_id="drone-mini",
            variant_id="mini-standard",
        ),
    ],
    ids=["wrong-product-variant", "wrong-store"],
)
def test_evidence_scope_mismatch_fails_closed(
    evidence_scope: ObjectScope,
) -> None:
    with pytest.raises(_ComposerDiagnostic) as error:
        _compose_answer(_payload(evidence_scope=evidence_scope))

    assert error.value.code is InternalDiagnosticCode.EVIDENCE_SCOPE_MISMATCH


def test_product_card_scope_mismatch_is_output_diagnostic() -> None:
    wrong_card = ObjectScope(
        store_id="store-drone-cn",
        product_id="drone-mini",
        variant_id="mini-explorer",
    )

    with pytest.raises(_ComposerDiagnostic) as error:
        _compose_answer(
            _payload(
                evidence_scope=ObjectScope(
                    store_id="store-drone-cn",
                    product_id="drone-mini",
                    variant_id="mini-standard",
                ),
                product_card=wrong_card,
            )
        )

    assert error.value.code is InternalDiagnosticCode.OUTPUT_SCOPE_MISMATCH


def test_missing_binding_is_output_diagnostic() -> None:
    with pytest.raises(_ComposerDiagnostic) as error:
        _compose_answer(
            _payload(
                evidence_scope=ObjectScope(
                    store_id="store-drone-cn",
                    product_id="drone-mini",
                    variant_id="mini-standard",
                ),
                with_binding=False,
            )
        )

    assert error.value.code is InternalDiagnosticCode.OUTPUT_SCOPE_MISMATCH


def test_dynamic_missing_freshness_is_not_composable() -> None:
    with pytest.raises(_ComposerDiagnostic) as error:
        _compose_answer(
            _payload(
                evidence_scope=ObjectScope(
                    store_id="store-drone-cn",
                    product_id="drone-mini",
                    variant_id="mini-standard",
                ),
                evidence_observed_at=None,
                fact_observed_at=None,
            )
        )

    assert error.value.code is InternalDiagnosticCode.DYNAMIC_FACT_FRESHNESS_MISSING


def test_sensitive_trace_values_are_redacted() -> None:
    assert _safe_trace_value("Authorization: Bearer super-secret") == "[REDACTED]"
    assert _safe_trace_value("store-drone-cn") == "store-drone-cn"
