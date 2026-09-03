"""Versioned public contracts for the Slice 1 product-facts boundary."""

from enum import StrEnum
from typing import Annotated, Any, Final, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    RootModel,
    StrictBool,
    StringConstraints,
    model_validator,
)

SCHEMA_VERSION: Final = "1.0"
TURN_REQUEST_VALIDATION_HTTP_STATUS: Final = 422
TURN_REQUEST_VALIDATION_MESSAGE: Final = "Request validation failed."

type SchemaVersion = Literal["1.0"]
type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class WireModel(BaseModel):
    """Strict public model with one shared JSON serialization path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_wire(self) -> dict[str, Any]:
        """Return JSON-compatible data while omitting absent optional fields."""
        return self.model_dump(mode="json", exclude_none=True)

    def to_wire_json(self) -> str:
        """Return JSON for the public wire boundary."""
        return self.model_dump_json(exclude_none=True)


class ConversationRef(WireModel):
    conversation_id: NonEmptyString
    message_id: NonEmptyString


class PageContext(WireModel):
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None


class ObjectScope(WireModel):
    """Reusable store/product/optional-variant scope, not a catalog identity type."""

    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None


class TurnRequest(WireModel):
    schema_version: SchemaVersion
    store_id: NonEmptyString
    conversation: ConversationRef
    user_text: NonEmptyString
    locale: NonEmptyString
    page_context: PageContext


class AttributeStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AttributeValue(WireModel):
    status: AttributeStatus
    value: JsonValue | None = None
    unit: NonEmptyString | None = None
    source_ref: NonEmptyString
    observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_status_value_shape(self) -> "AttributeValue":
        value_was_supplied = "value" in self.model_fields_set
        if self.status is AttributeStatus.KNOWN:
            if not value_was_supplied or self.value is None:
                raise ValueError("KNOWN attributes require a non-null value")
        elif value_was_supplied:
            raise ValueError("UNKNOWN and NOT_APPLICABLE attributes must omit value")
        return self


class ProductRecord(WireModel):
    store_id: NonEmptyString
    product_id: NonEmptyString
    display_title: NonEmptyString
    shared_attributes: dict[NonEmptyString, AttributeValue]
    variant_ids: list[NonEmptyString]


class VariantRecord(WireModel):
    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString
    display_label: NonEmptyString
    options: dict[NonEmptyString, NonEmptyString]
    variant_attributes: dict[NonEmptyString, AttributeValue]


class ToolStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


class ToolErrorCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    VARIANT_NOT_FOUND = "VARIANT_NOT_FOUND"
    PARTIAL_RESULT = "PARTIAL_RESULT"


class ToolResult[ToolDataT](WireModel):
    status: ToolStatus
    data: ToolDataT | None = None
    source: NonEmptyString
    observed_at: AwareDatetime
    error_code: ToolErrorCode | None = None
    retryable: StrictBool
    missing_fields: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> "ToolResult[ToolDataT]":
        data_was_supplied = "data" in self.model_fields_set

        if self.status is ToolStatus.SUCCESS:
            if not data_was_supplied or self.data is None:
                raise ValueError("SUCCESS requires non-null typed data")
            if self.error_code is not None or self.missing_fields:
                raise ValueError("SUCCESS cannot carry an error code or missing fields")
        elif self.status is ToolStatus.PARTIAL:
            if not data_was_supplied or self.data is None:
                raise ValueError("PARTIAL requires non-null typed data")
            if not self.missing_fields:
                raise ValueError("PARTIAL requires explicit missing fields")
            if self.error_code not in (None, ToolErrorCode.PARTIAL_RESULT):
                raise ValueError("PARTIAL cannot carry a non-partial error code")
        else:
            if data_was_supplied:
                raise ValueError("ERROR must omit data")
            if self.error_code is None:
                raise ValueError("ERROR requires a distinguishable error code")
            if self.error_code is ToolErrorCode.PARTIAL_RESULT:
                raise ValueError("ERROR cannot use the PARTIAL_RESULT code")
            if self.missing_fields:
                raise ValueError("ERROR cannot carry partial missing fields")
        return self


class RouteIntent(StrEnum):
    PRODUCT_QA = "PRODUCT_QA"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class RouteAction(StrEnum):
    READ_PRODUCT_FACT = "READ_PRODUCT_FACT"
    READ_VARIANT_FACT = "READ_VARIANT_FACT"
    REQUEST_VARIANT_CLARIFICATION = "REQUEST_VARIANT_CLARIFICATION"
    RETURN_FALLBACK = "RETURN_FALLBACK"


class FieldScope(StrEnum):
    PRODUCT_SHARED = "PRODUCT_SHARED"
    VARIANT_SPECIFIC = "VARIANT_SPECIFIC"
    DYNAMIC_VARIANT = "DYNAMIC_VARIANT"


class MinimalRouteDecision(WireModel):
    intent: RouteIntent
    action: RouteAction
    requested_field: NonEmptyString | None = None
    field_scope: FieldScope | None = None
    resolved_scope: ObjectScope
    reason: NonEmptyString

    @model_validator(mode="after")
    def validate_intent_shape(self) -> "MinimalRouteDecision":
        if self.intent is RouteIntent.PRODUCT_QA:
            if self.requested_field is None or self.field_scope is None:
                raise ValueError("PRODUCT_QA requires requested_field and field_scope")
        else:
            if self.action is not RouteAction.RETURN_FALLBACK:
                raise ValueError("OUT_OF_SCOPE must use RETURN_FALLBACK")
            if {
                "requested_field",
                "field_scope",
            } & self.model_fields_set:
                raise ValueError(
                    "OUT_OF_SCOPE must omit requested_field and field_scope"
                )
        return self


class EvidenceType(StrEnum):
    TOOL = "TOOL"


class Evidence(WireModel):
    evidence_id: NonEmptyString
    type: EvidenceType
    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    field_locator: NonEmptyString
    fact: AttributeValue
    source: NonEmptyString
    observed_at: AwareDatetime | None = None


class Claim(WireModel):
    claim_id: NonEmptyString
    field: NonEmptyString
    fact: AttributeValue


class ClaimEvidenceBinding(WireModel):
    claim_id: NonEmptyString
    evidence_ids: list[NonEmptyString] = Field(min_length=1)


class ProductCard(WireModel):
    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString | None = None
    display_title: NonEmptyString


class FreshnessDisclosure(WireModel):
    observed_at: AwareDatetime
    source: NonEmptyString


class FallbackReasonCode(StrEnum):
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    VARIANT_NOT_FOUND = "VARIANT_NOT_FOUND"
    VARIANT_REQUIRED = "VARIANT_REQUIRED"
    FACT_UNKNOWN_OR_MISSING = "FACT_UNKNOWN_OR_MISSING"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_RATE_LIMITED = "TOOL_RATE_LIMITED"
    TOOL_UNAUTHORIZED = "TOOL_UNAUTHORIZED"
    TOOL_PARTIAL_RESULT = "TOOL_PARTIAL_RESULT"
    INTERNAL_CONSISTENCY_ERROR = "INTERNAL_CONSISTENCY_ERROR"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class StandardFallback(WireModel):
    reason_code: FallbackReasonCode
    message: NonEmptyString
    retryable: StrictBool
    next_actions: list[NonEmptyString] = Field(min_length=1)
    resolved_scope: ObjectScope | None = None


class EnvelopeOutcome(StrEnum):
    ANSWER = "ANSWER"
    FALLBACK = "FALLBACK"


class ConversationStateProjection(WireModel):
    """Optional server-authoritative state supplied with an accepted turn.

    The projection intentionally contains only replay-safe state.  It is not a
    request DTO and clients must not send it back as authoritative input.
    """

    active_constraints: tuple[JsonValue, ...] = ()
    pending_clarification: JsonValue | None = None
    pending_switch: JsonValue | None = None
    revision: int = Field(ge=0)


class EnvelopeBase(WireModel):
    schema_version: SchemaVersion
    conversation: ConversationRef
    trace_correlation_id: NonEmptyString
    resolved_scope: ObjectScope
    text: NonEmptyString
    claims: list[Claim] = Field(default_factory=list)
    product_card: ProductCard | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    bindings: list[ClaimEvidenceBinding] = Field(default_factory=list)
    freshness: FreshnessDisclosure | None = None
    conversation_state: ConversationStateProjection | None = None


class AnswerPayload(EnvelopeBase):
    outcome: Literal[EnvelopeOutcome.ANSWER]


class FallbackPayload(EnvelopeBase):
    outcome: Literal[EnvelopeOutcome.FALLBACK]
    fallback: StandardFallback


type EnvelopePayload = Annotated[
    AnswerPayload | FallbackPayload, Field(discriminator="outcome")
]


class AnswerEnvelope(RootModel[EnvelopePayload]):
    """Discriminated final response; no streaming event is part of this contract."""

    model_config = ConfigDict(frozen=True)

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def to_wire_json(self) -> str:
        return self.model_dump_json(exclude_none=True)


class InternalDiagnosticCode(StrEnum):
    EVIDENCE_SCOPE_MISMATCH = "EVIDENCE_SCOPE_MISMATCH"
    OUTPUT_SCOPE_MISMATCH = "OUTPUT_SCOPE_MISMATCH"
    DYNAMIC_FACT_FRESHNESS_MISSING = "DYNAMIC_FACT_FRESHNESS_MISSING"


class TraceEventType(StrEnum):
    TURN_REQUEST_ACCEPTED = "TURN_REQUEST_ACCEPTED"
    TURN_REQUEST_REJECTED = "TURN_REQUEST_REJECTED"
    PAGE_CONTEXT_RESOLVED = "PAGE_CONTEXT_RESOLVED"
    PAGE_CONTEXT_REJECTED = "PAGE_CONTEXT_REJECTED"
    ROUTE_DECISION = "ROUTE_DECISION"
    SHOPIFY_READ_CALLED = "SHOPIFY_READ_CALLED"
    TOOL_RESULT = "TOOL_RESULT"
    EVIDENCE_ACCEPTED = "EVIDENCE_ACCEPTED"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    ANSWER_PRODUCED = "ANSWER_PRODUCED"
    FALLBACK_PRODUCED = "FALLBACK_PRODUCED"


class TraceResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    ANSWER = "ANSWER"
    FALLBACK = "FALLBACK"


class TraceOperation(StrEnum):
    GET_PRODUCTS = "get_products"
    GET_VARIANTS = "get_variants"
    REFRESH_COMMERCE_STATE = "refresh_commerce_state"


class TraceSummary(WireModel):
    result: TraceResult
    scope: ObjectScope | None = None
    operation: TraceOperation | None = None
    tool_status: ToolStatus | None = None
    fallback_reason: FallbackReasonCode | None = None
    diagnostic_code: InternalDiagnosticCode | None = None


class TraceEvent(WireModel):
    schema_version: SchemaVersion
    correlation_id: NonEmptyString
    event_type: TraceEventType
    occurred_at: AwareDatetime
    summary: TraceSummary


class TurnRequestValidationResponse(WireModel):
    """Stable transport rejection body, deliberately not an AnswerEnvelope."""

    schema_version: SchemaVersion
    error_code: Literal["INVALID_TURN_REQUEST"]
    message: Literal[TURN_REQUEST_VALIDATION_MESSAGE]
