"""Contract coverage for the approved Slice 1 wire models."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import backend.common as public_contracts
from backend.common import (
    SCHEMA_VERSION,
    TURN_REQUEST_VALIDATION_HTTP_STATUS,
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
    FieldScope,
    FreshnessDisclosure,
    InternalDiagnosticCode,
    MinimalRouteDecision,
    ObjectScope,
    ProductCard,
    ProductRecord,
    RouteAction,
    RouteIntent,
    StandardFallback,
    ToolErrorCode,
    ToolResult,
    ToolStatus,
    TraceEvent,
    TraceEventType,
    TraceResult,
    TraceSummary,
    TurnRequest,
    TurnRequestValidationResponse,
    VariantRecord,
)

pytestmark = pytest.mark.contract

OBSERVED_AT = datetime(2026, 8, 30, 8, 15, tzinfo=UTC)


def valid_turn_data() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "store_id": "store-1",
        "conversation": {
            "conversation_id": "conversation-1",
            "message_id": "message-1",
        },
        "user_text": "这个版本的重量是多少？",
        "locale": "zh-CN",
        "page_context": {"product_id": "product-1", "variant_id": "variant-1"},
    }


def conversation_ref() -> ConversationRef:
    return ConversationRef(
        conversation_id="conversation-1",
        message_id="message-1",
    )


def resolved_scope() -> ObjectScope:
    return ObjectScope(
        store_id="store-1",
        product_id="product-1",
        variant_id="variant-1",
    )


def known_weight() -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=249,
        unit="g",
        source_ref="fixture://products/product-1/variants/variant-1#weight",
        observed_at=OBSERVED_AT,
    )


def product_record() -> ProductRecord:
    return ProductRecord(
        store_id="store-1",
        product_id="product-1",
        display_title="Drone One",
        shared_attributes={
            "manufacturer": AttributeValue(
                status=AttributeStatus.KNOWN,
                value="Example",
                source_ref="fixture://products/product-1#manufacturer",
            )
        },
        variant_ids=["variant-1", "variant-2"],
    )


def evidence() -> Evidence:
    return Evidence(
        evidence_id="evidence-1",
        type=EvidenceType.TOOL,
        store_id="store-1",
        product_id="product-1",
        variant_id="variant-1",
        field_locator="variants.variant-1.attributes.weight",
        fact=known_weight(),
        source="fixture://products/product-1/variants/variant-1",
        observed_at=OBSERVED_AT,
    )


def answer_payload() -> AnswerPayload:
    return AnswerPayload(
        schema_version=SCHEMA_VERSION,
        outcome=EnvelopeOutcome.ANSWER,
        conversation=conversation_ref(),
        trace_correlation_id="correlation-1",
        resolved_scope=resolved_scope(),
        text="该变体重量为 249 g。",
        claims=[Claim(claim_id="claim-1", field="weight", fact=known_weight())],
        evidence=[evidence()],
        bindings=[
            ClaimEvidenceBinding(
                claim_id="claim-1",
                evidence_ids=["evidence-1"],
            )
        ],
        freshness=FreshnessDisclosure(
            observed_at=OBSERVED_AT,
            source="fixture://products/product-1/variants/variant-1",
        ),
    )


def fallback_payload() -> FallbackPayload:
    return FallbackPayload(
        schema_version=SCHEMA_VERSION,
        outcome=EnvelopeOutcome.FALLBACK,
        conversation=conversation_ref(),
        trace_correlation_id="correlation-1",
        resolved_scope=resolved_scope(),
        text="请先选择具体变体。",
        fallback=StandardFallback(
            reason_code=FallbackReasonCode.VARIANT_REQUIRED,
            message="该信息取决于具体变体。",
            retryable=False,
            next_actions=["选择一个变体"],
            resolved_scope=resolved_scope(),
        ),
    )


def test_valid_turn_request_serializes_and_round_trips() -> None:
    request = TurnRequest.model_validate(valid_turn_data())

    wire = request.to_wire()
    restored = TurnRequest.model_validate_json(request.to_wire_json())

    assert wire == valid_turn_data()
    assert restored == request
    assert "state_revision" not in wire


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ((), "schema_version"),
        ((), "store_id"),
        ((), "conversation"),
        ((), "user_text"),
        ((), "locale"),
        ((), "page_context"),
        (("conversation",), "conversation_id"),
        (("conversation",), "message_id"),
        (("page_context",), "product_id"),
    ],
)
def test_turn_request_rejects_missing_required_scope(
    path: tuple[str, ...], key: str
) -> None:
    data = valid_turn_data()
    target = data
    for component in path:
        target = target[component]  # type: ignore[assignment,index]
    del target[key]  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        TurnRequest.model_validate(data)


def test_turn_request_accepts_product_only_page_context() -> None:
    data = valid_turn_data()
    page_context = data["page_context"]
    assert isinstance(page_context, dict)
    del page_context["variant_id"]

    request = TurnRequest.model_validate(data)

    assert request.page_context.variant_id is None
    assert "variant_id" not in request.to_wire()["page_context"]


def test_turn_request_rejects_invalid_schema_version() -> None:
    data = valid_turn_data()
    data["schema_version"] = "2.0"

    with pytest.raises(ValidationError):
        TurnRequest.model_validate(data)


@pytest.mark.parametrize("extra_field", ["state_revision", "future_field"])
def test_turn_request_rejects_unapproved_fields(extra_field: str) -> None:
    data = valid_turn_data()
    data[extra_field] = 1

    with pytest.raises(ValidationError):
        TurnRequest.model_validate(data)


def test_nested_contracts_also_reject_future_fields() -> None:
    data = valid_turn_data()
    page_context = data["page_context"]
    assert isinstance(page_context, dict)
    page_context["future_field"] = "not-approved"

    with pytest.raises(ValidationError):
        TurnRequest.model_validate(data)


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (
            AttributeValue,
            {"status": "MISSING", "source_ref": "fixture://field"},
        ),
        (
            MinimalRouteDecision,
            {
                "intent": "RECOMMENDATION",
                "action": RouteAction.RETURN_FALLBACK,
                "requested_field": "recommendation",
                "field_scope": FieldScope.PRODUCT_SHARED,
                "resolved_scope": resolved_scope().to_wire(),
                "reason": "unsupported",
            },
        ),
    ],
)
def test_contracts_reject_invalid_enums(
    model: type[AttributeValue] | type[MinimalRouteDecision],
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_minimal_route_decision_preserves_declared_field_scope() -> None:
    decision = MinimalRouteDecision(
        intent=RouteIntent.PRODUCT_QA,
        action=RouteAction.READ_VARIANT_FACT,
        requested_field="weight",
        field_scope=FieldScope.VARIANT_SPECIFIC,
        resolved_scope=resolved_scope(),
        reason="The requested field belongs to the selected variant.",
    )

    assert decision.to_wire()["field_scope"] == "VARIANT_SPECIFIC"


def test_out_of_scope_route_uses_fallback_and_omits_field_semantics() -> None:
    decision = MinimalRouteDecision(
        intent=RouteIntent.OUT_OF_SCOPE,
        action=RouteAction.RETURN_FALLBACK,
        resolved_scope=resolved_scope(),
        reason="The request is outside product fact questions.",
    )

    wire = decision.to_wire()
    assert wire["action"] == "RETURN_FALLBACK"
    assert "requested_field" not in wire
    assert "field_scope" not in wire
    assert MinimalRouteDecision.model_validate_json(decision.to_wire_json()) == decision


@pytest.mark.parametrize(
    "action",
    [
        RouteAction.READ_PRODUCT_FACT,
        RouteAction.READ_VARIANT_FACT,
        RouteAction.REQUEST_VARIANT_CLARIFICATION,
    ],
)
def test_out_of_scope_route_rejects_non_fallback_actions(
    action: RouteAction,
) -> None:
    with pytest.raises(ValidationError):
        MinimalRouteDecision(
            intent=RouteIntent.OUT_OF_SCOPE,
            action=action,
            resolved_scope=resolved_scope(),
            reason="The request is outside product fact questions.",
        )


@pytest.mark.parametrize(
    "field_semantics",
    [
        {"requested_field": "price"},
        {"field_scope": FieldScope.DYNAMIC_VARIANT},
        {
            "requested_field": "price",
            "field_scope": FieldScope.DYNAMIC_VARIANT,
        },
        {"requested_field": None},
        {"field_scope": None},
    ],
)
def test_out_of_scope_route_rejects_invented_field_semantics(
    field_semantics: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MinimalRouteDecision(
            intent=RouteIntent.OUT_OF_SCOPE,
            action=RouteAction.RETURN_FALLBACK,
            resolved_scope=resolved_scope(),
            reason="The request is outside product fact questions.",
            **field_semantics,
        )


@pytest.mark.parametrize(
    "field_semantics",
    [
        {},
        {"requested_field": "weight"},
        {"field_scope": FieldScope.VARIANT_SPECIFIC},
    ],
)
def test_product_qa_route_requires_field_and_scope(
    field_semantics: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MinimalRouteDecision(
            intent=RouteIntent.PRODUCT_QA,
            action=RouteAction.READ_VARIANT_FACT,
            resolved_scope=resolved_scope(),
            reason="The request is a product fact question.",
            **field_semantics,
        )


def test_attribute_value_enforces_known_value_invariant() -> None:
    with pytest.raises(ValidationError):
        AttributeValue(status=AttributeStatus.KNOWN, source_ref="fixture://field")

    known = known_weight()

    assert known.value == 249


@pytest.mark.parametrize(
    "status", [AttributeStatus.UNKNOWN, AttributeStatus.NOT_APPLICABLE]
)
@pytest.mark.parametrize("fake_value", [False, 0, "", None])
def test_non_known_attribute_cannot_carry_a_value(
    status: AttributeStatus, fake_value: object
) -> None:
    with pytest.raises(ValidationError):
        AttributeValue(
            status=status,
            value=fake_value,
            source_ref="fixture://field",
        )


def test_attribute_time_is_timezone_aware_and_stably_serialized() -> None:
    wire = known_weight().to_wire()

    assert wire["observed_at"] == "2026-08-30T08:15:00Z"

    with pytest.raises(ValidationError):
        AttributeValue(
            status=AttributeStatus.KNOWN,
            value=249,
            source_ref="fixture://field",
            observed_at=datetime(2026, 8, 30, 8, 15),
        )


def test_product_record_keeps_variant_references_identity_only() -> None:
    product = product_record()

    assert product.variant_ids == ["variant-1", "variant-2"]
    with pytest.raises(ValidationError):
        ProductRecord.model_validate(
            {
                **product.to_wire(),
                "variant_ids": [{"variant_id": "variant-1", "price": 100}],
            }
        )


def test_product_and_variant_attribute_schemas_do_not_mix() -> None:
    product_data = product_record().to_wire()
    product_data["variant_attributes"] = {}

    variant = VariantRecord(
        store_id="store-1",
        product_id="product-1",
        variant_id="variant-1",
        display_label="Standard",
        options={"color": "gray"},
        variant_attributes={"weight": known_weight()},
    )
    variant_data = variant.to_wire()
    variant_data["shared_attributes"] = {}

    with pytest.raises(ValidationError):
        ProductRecord.model_validate(product_data)
    with pytest.raises(ValidationError):
        VariantRecord.model_validate(variant_data)


def test_no_independent_product_or_variant_identity_type_is_exported() -> None:
    assert not hasattr(public_contracts, "ProductIdentity")
    assert not hasattr(public_contracts, "VariantIdentity")


def test_slice_one_evidence_rejects_unapproved_evidence_types() -> None:
    data = evidence().to_wire()
    data["type"] = "DOCUMENT"

    with pytest.raises(ValidationError):
        Evidence.model_validate(data)


def test_tool_result_success_shape_and_typed_round_trip() -> None:
    result = ToolResult[ProductRecord](
        status=ToolStatus.SUCCESS,
        data=product_record(),
        source="fixture://products/product-1",
        observed_at=OBSERVED_AT,
        retryable=False,
    )

    restored = ToolResult[ProductRecord].model_validate_json(result.to_wire_json())

    assert restored == result
    assert restored.data == product_record()


def test_tool_result_rejects_invalid_status_enum() -> None:
    with pytest.raises(ValidationError):
        ToolResult[ProductRecord].model_validate(
            {
                "status": "NULL",
                "data": product_record().to_wire(),
                "source": "fixture://products/product-1",
                "observed_at": OBSERVED_AT,
                "retryable": False,
            }
        )


def test_tool_result_success_requires_data() -> None:
    with pytest.raises(ValidationError):
        ToolResult[ProductRecord](
            status=ToolStatus.SUCCESS,
            source="fixture://products/product-1",
            observed_at=OBSERVED_AT,
            retryable=False,
        )


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"error_code": ToolErrorCode.TIMEOUT},
        {"missing_fields": ["weight"]},
    ],
)
def test_tool_result_success_rejects_error_or_partial_fields(
    invalid_fields: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ToolResult[ProductRecord](
            status=ToolStatus.SUCCESS,
            data=product_record(),
            source="fixture://products/product-1",
            observed_at=OBSERVED_AT,
            retryable=False,
            **invalid_fields,
        )


def test_tool_result_partial_requires_data_and_missing_fields() -> None:
    partial = ToolResult[list[str]](
        status=ToolStatus.PARTIAL,
        data=["available-field"],
        source="fixture://products/product-1",
        observed_at=OBSERVED_AT,
        error_code=ToolErrorCode.PARTIAL_RESULT,
        retryable=True,
        missing_fields=["requested-field"],
    )

    assert partial.status is ToolStatus.PARTIAL
    assert partial.missing_fields == ["requested-field"]

    with pytest.raises(ValidationError):
        ToolResult[list[str]](
            status=ToolStatus.PARTIAL,
            data=["available-field"],
            source="fixture://products/product-1",
            observed_at=OBSERVED_AT,
            retryable=True,
        )
    with pytest.raises(ValidationError):
        ToolResult[list[str]](
            status=ToolStatus.PARTIAL,
            source="fixture://products/product-1",
            observed_at=OBSERVED_AT,
            retryable=True,
            missing_fields=["requested-field"],
        )
    with pytest.raises(ValidationError):
        ToolResult[list[str]](
            status=ToolStatus.PARTIAL,
            data=["available-field"],
            source="fixture://products/product-1",
            observed_at=OBSERVED_AT,
            error_code=ToolErrorCode.TIMEOUT,
            retryable=True,
            missing_fields=["requested-field"],
        )


@pytest.mark.parametrize(
    "error_code",
    [
        ToolErrorCode.TIMEOUT,
        ToolErrorCode.RATE_LIMITED,
        ToolErrorCode.UNAUTHORIZED,
        ToolErrorCode.PRODUCT_NOT_FOUND,
        ToolErrorCode.VARIANT_NOT_FOUND,
    ],
)
def test_tool_error_codes_remain_distinguishable(
    error_code: ToolErrorCode,
) -> None:
    result = ToolResult[ProductRecord](
        status=ToolStatus.ERROR,
        source="fixture://products/product-1",
        observed_at=OBSERVED_AT,
        error_code=error_code,
        retryable=error_code
        in {
            ToolErrorCode.TIMEOUT,
            ToolErrorCode.RATE_LIMITED,
        },
    )

    assert result.to_wire()["error_code"] == error_code.value
    assert "data" not in result.to_wire()


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {},
        {"data": None, "error_code": ToolErrorCode.TIMEOUT},
        {"error_code": ToolErrorCode.PARTIAL_RESULT},
        {
            "error_code": ToolErrorCode.TIMEOUT,
            "missing_fields": ["requested-field"],
        },
    ],
)
def test_tool_result_rejects_invalid_error_shapes(
    invalid_fields: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ToolResult[ProductRecord](
            status=ToolStatus.ERROR,
            source="fixture://products/product-1",
            observed_at=OBSERVED_AT,
            retryable=False,
            **invalid_fields,
        )


def test_tool_result_requires_observed_at_and_strict_retryable() -> None:
    with pytest.raises(ValidationError):
        ToolResult[ProductRecord](
            status=ToolStatus.SUCCESS,
            data=product_record(),
            source="fixture://products/product-1",
            retryable=False,
        )
    with pytest.raises(ValidationError):
        ToolResult[ProductRecord](
            status=ToolStatus.SUCCESS,
            data=product_record(),
            source="fixture://products/product-1",
            observed_at=OBSERVED_AT,
            retryable="false",
        )


def test_answer_and_fallback_are_discriminated_and_round_trip() -> None:
    answer = AnswerEnvelope(root=answer_payload())
    fallback = AnswerEnvelope(root=fallback_payload())

    answer_wire = answer.to_wire()
    fallback_wire = fallback.to_wire()

    assert answer_wire["outcome"] == "ANSWER"
    assert "fallback" not in answer_wire
    assert "product_card" not in answer_wire
    assert fallback_wire["outcome"] == "FALLBACK"
    assert fallback_wire["fallback"]["reason_code"] == "VARIANT_REQUIRED"
    assert AnswerEnvelope.model_validate_json(answer.to_wire_json()) == answer
    assert AnswerEnvelope.model_validate_json(fallback.to_wire_json()) == fallback


def test_product_card_is_optional_but_has_explicit_scope_when_present() -> None:
    payload_data = answer_payload().to_wire()
    payload_data["product_card"] = ProductCard(
        store_id="store-1",
        product_id="product-1",
        variant_id="variant-1",
        display_title="Drone One - Standard",
    ).to_wire()

    envelope = AnswerEnvelope.model_validate(payload_data)

    assert envelope.to_wire()["product_card"]["variant_id"] == "variant-1"


def test_answer_and_fallback_reject_the_other_shape() -> None:
    answer_data = answer_payload().to_wire()
    answer_data["fallback"] = fallback_payload().fallback.to_wire()
    fallback_data = fallback_payload().to_wire()
    del fallback_data["fallback"]

    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(answer_data)
    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(fallback_data)


def test_answer_envelope_rejects_invalid_version_and_future_fields() -> None:
    invalid_version = answer_payload().to_wire()
    invalid_version["schema_version"] = "2.0"

    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(invalid_version)

    for future_field in (
        "recommendations",
        "comparison",
        "constraints",
        "state",
        "rag",
        "stream_event",
    ):
        data = answer_payload().to_wire()
        data[future_field] = {}
        with pytest.raises(ValidationError):
            AnswerEnvelope.model_validate(data)


def test_fallback_requires_message_retryable_and_next_action() -> None:
    base = {
        "reason_code": FallbackReasonCode.OUT_OF_SCOPE,
        "message": "当前仅支持商品事实问题。",
        "retryable": False,
        "next_actions": ["询问当前商品的参数"],
    }

    for missing_field in ("message", "retryable", "next_actions"):
        invalid = dict(base)
        del invalid[missing_field]
        with pytest.raises(ValidationError):
            StandardFallback.model_validate(invalid)

    with pytest.raises(ValidationError):
        StandardFallback.model_validate({**base, "next_actions": []})


def test_public_fallback_reason_code_set_is_exact() -> None:
    expected = {
        "PRODUCT_NOT_FOUND",
        "VARIANT_NOT_FOUND",
        "VARIANT_REQUIRED",
        "FACT_UNKNOWN_OR_MISSING",
        "TOOL_TIMEOUT",
        "TOOL_RATE_LIMITED",
        "TOOL_UNAUTHORIZED",
        "TOOL_PARTIAL_RESULT",
        "INTERNAL_CONSISTENCY_ERROR",
        "OUT_OF_SCOPE",
    }
    internal = {member.value for member in InternalDiagnosticCode}

    assert {member.value for member in FallbackReasonCode} == expected
    assert expected.isdisjoint(internal)
    assert "EVIDENCE_SCOPE_MISMATCH" not in expected


def test_invalid_turn_request_has_stable_safe_transport_rejection() -> None:
    response = TurnRequestValidationResponse(
        schema_version=SCHEMA_VERSION,
        error_code="INVALID_TURN_REQUEST",
        message="Request validation failed.",
    )
    body = response.to_wire()

    assert TURN_REQUEST_VALIDATION_HTTP_STATUS == 422
    assert body == {
        "schema_version": SCHEMA_VERSION,
        "error_code": "INVALID_TURN_REQUEST",
        "message": "Request validation failed.",
    }
    assert "outcome" not in body
    assert not {"details", "errors", "exception", "schema", "stack"} & body.keys()
    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(body)
    with pytest.raises(ValidationError):
        TurnRequestValidationResponse.model_validate(
            {"error_code": "INVALID_TURN_REQUEST"}
        )


def test_trace_event_accepts_only_allowlisted_safe_summary() -> None:
    event = TraceEvent(
        schema_version=SCHEMA_VERSION,
        correlation_id="correlation-1",
        event_type=TraceEventType.EVIDENCE_REJECTED,
        occurred_at=OBSERVED_AT,
        summary=TraceSummary(
            result=TraceResult.REJECTED,
            scope=resolved_scope(),
            diagnostic_code=InternalDiagnosticCode.EVIDENCE_SCOPE_MISMATCH,
        ),
    )

    assert event.to_wire()["summary"]["diagnostic_code"] == ("EVIDENCE_SCOPE_MISMATCH")


def test_trace_operation_uses_the_read_allowlist_name() -> None:
    summary = TraceSummary(
        result=TraceResult.ACCEPTED,
        scope=resolved_scope(),
        operation="get_variants",
    )

    assert summary.to_wire()["operation"] == "get_variants"


@pytest.mark.parametrize(
    "unsafe_field",
    ["headers", "token", "secret", "credential", "stack", "payload"],
)
def test_trace_event_rejects_sensitive_or_arbitrary_payload(
    unsafe_field: str,
) -> None:
    data = {
        "schema_version": SCHEMA_VERSION,
        "correlation_id": "correlation-1",
        "event_type": TraceEventType.TURN_REQUEST_REJECTED,
        "occurred_at": OBSERVED_AT,
        "summary": {"result": TraceResult.REJECTED},
        unsafe_field: "must-not-be-stored",
    }

    with pytest.raises(ValidationError):
        TraceEvent.model_validate(data)

    summary_data = {"result": TraceResult.REJECTED, unsafe_field: "unsafe"}
    with pytest.raises(ValidationError):
        TraceSummary.model_validate(summary_data)


def test_wire_json_schemas_are_serializable_and_discriminated() -> None:
    turn_schema = TurnRequest.model_json_schema()
    envelope_schema = AnswerEnvelope.model_json_schema()
    transport_schema = TurnRequestValidationResponse.model_json_schema()

    json.dumps(turn_schema)
    json.dumps(envelope_schema)
    json.dumps(transport_schema)

    schema_version_ref = turn_schema["properties"]["schema_version"]["$ref"]
    schema_version_name = schema_version_ref.rsplit("/", maxsplit=1)[-1]
    assert turn_schema["$defs"][schema_version_name]["const"] == SCHEMA_VERSION
    assert set(turn_schema["required"]) == {
        "schema_version",
        "store_id",
        "conversation",
        "user_text",
        "locale",
        "page_context",
    }
    envelope_root_name = envelope_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    envelope_union = envelope_schema["$defs"][envelope_root_name]
    assert envelope_union["discriminator"]["propertyName"] == "outcome"
    assert len(envelope_union["oneOf"]) == 2


def test_state_revision_and_stream_event_are_not_defined() -> None:
    turn_schema_text = json.dumps(TurnRequest.model_json_schema())
    envelope_schema_text = json.dumps(AnswerEnvelope.model_json_schema())

    assert "state_revision" not in turn_schema_text
    assert "STREAM_CHUNK" not in envelope_schema_text
    assert not hasattr(public_contracts, "StreamEvent")
