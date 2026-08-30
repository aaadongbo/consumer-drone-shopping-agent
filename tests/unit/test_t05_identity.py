"""T05 unit gates for field scope, exact identity, and no default selection."""

from datetime import UTC, datetime

import pytest

from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    AttributeStatus,
    AttributeValue,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    FieldScope,
    PageContext,
    ProductRecord,
    RouteAction,
    ToolErrorCode,
    ToolResult,
    ToolStatus,
    TraceEventType,
    TurnRequest,
    VariantRecord,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 30, 11, 0, tzinfo=UTC)


def _request(
    question: str,
    *,
    product_id: str = "drone-mini",
    variant_id: str | None = None,
) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(
            conversation_id="conversation-t05-unit",
            message_id="message-t05-unit",
        ),
        user_text=question,
        locale="zh-CN",
        page_context=PageContext(product_id=product_id, variant_id=variant_id),
    )


def _known(value: object, field: str) -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=value,
        source_ref=f"controlled://{field}",
    )


def _product(
    *, store_id: str = "store-drone-cn", product_id: str = "drone-mini"
) -> ProductRecord:
    return ProductRecord(
        store_id=store_id,
        product_id=product_id,
        display_title="Controlled Product",
        shared_attributes={"manufacturer": _known("Controlled Maker", "manufacturer")},
        variant_ids=["must-not-be-selected", "also-not-selected"],
    )


def _variant(
    *,
    store_id: str = "store-drone-cn",
    product_id: str = "drone-mini",
    variant_id: str = "mini-standard",
) -> VariantRecord:
    return VariantRecord(
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        display_label="Controlled Variant",
        options={"bundle": "controlled"},
        variant_attributes={"battery_count": _known(9, "battery_count")},
    )


def _success(data) -> ToolResult:
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data=data,
        source="controlled://result",
        observed_at=NOW,
        retryable=False,
    )


def _not_found(error_code: ToolErrorCode) -> ToolResult:
    return ToolResult(
        status=ToolStatus.ERROR,
        source="controlled://not-found",
        observed_at=NOW,
        error_code=error_code,
        retryable=False,
    )


class _ControlledShopifyPort:
    def __init__(
        self,
        *,
        products: ToolResult | None = None,
        variants: ToolResult | None = None,
    ) -> None:
        self.products = products
        self.variants = variants
        self.product_calls = 0
        self.variant_calls = 0
        self.commerce_calls = 0

    def get_products(self, *, store_id: str, product_id: str) -> ToolResult:
        self.product_calls += 1
        assert self.products is not None
        return self.products

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ) -> ToolResult:
        self.variant_calls += 1
        assert self.variants is not None
        return self.variants

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult:
        self.commerce_calls += 1
        raise AssertionError("T05 must not read dynamic commerce")


def _service(
    port: _ControlledShopifyPort,
) -> tuple[Slice1ApplicationService, InMemoryTraceSink]:
    sink = InMemoryTraceSink()
    return (
        Slice1ApplicationService(
            shopify=port,
            interpreter=DeterministicQuestionInterpreter(),
            trace_sink=sink,
            correlation_id_factory=lambda: "correlation-t05-unit",
            clock=lambda: NOW,
        ),
        sink,
    )


@pytest.mark.parametrize(
    ("question", "variant_id", "field", "scope", "action"),
    [
        (
            "这款无人机的制造商是谁？",
            None,
            "manufacturer",
            FieldScope.PRODUCT_SHARED,
            RouteAction.READ_PRODUCT_FACT,
        ),
        (
            "这个套装有几块电池？",
            "mini-standard",
            "battery_count",
            FieldScope.VARIANT_SPECIFIC,
            RouteAction.READ_VARIANT_FACT,
        ),
        (
            "这款现在多少钱？",
            "mini-standard",
            "price",
            FieldScope.DYNAMIC_VARIANT,
            RouteAction.READ_VARIANT_FACT,
        ),
    ],
)
def test_interpreter_classifies_fixed_field_scopes(
    question: str,
    variant_id: str | None,
    field: str,
    scope: FieldScope,
    action: RouteAction,
) -> None:
    decision = DeterministicQuestionInterpreter().interpret(
        _request(question, variant_id=variant_id)
    )

    assert decision.requested_field == field
    assert decision.field_scope is scope
    assert decision.action is action


def test_dynamic_price_classification_remains_variant_scoped() -> None:
    decision = DeterministicQuestionInterpreter().interpret(
        _request("这款现在多少钱？", variant_id="mini-standard")
    )

    assert decision.field_scope is FieldScope.DYNAMIC_VARIANT
    assert decision.action is RouteAction.READ_VARIANT_FACT
    assert decision.resolved_scope.variant_id == "mini-standard"


@pytest.mark.parametrize(
    "records",
    [
        [_product(store_id="foreign-store")],
        [_product(product_id="drone-cine")],
        [],
        [_product(), _product(product_id="drone-cine")],
    ],
    ids=["store-mismatch", "product-mismatch", "empty", "multiple"],
)
def test_product_success_requires_one_exact_identity(
    records: list[ProductRecord],
) -> None:
    port = _ControlledShopifyPort(products=_success(records))
    service, sink = _service(port)

    payload = service.answer(_request("这款无人机的制造商是谁？")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.PRODUCT_NOT_FOUND
    assert (port.product_calls, port.variant_calls, port.commerce_calls) == (1, 0, 0)
    _assert_identity_failure_trace(sink)


@pytest.mark.parametrize(
    "records",
    [
        [_variant(store_id="foreign-store")],
        [_variant(product_id="drone-cine")],
        [_variant(variant_id="mini-explorer")],
        [],
        [_variant(), _variant(variant_id="mini-explorer")],
    ],
    ids=[
        "store-mismatch",
        "product-mismatch",
        "variant-mismatch",
        "empty",
        "multiple",
    ],
)
def test_variant_success_requires_one_exact_owned_identity(
    records: list[VariantRecord],
) -> None:
    port = _ControlledShopifyPort(variants=_success(records))
    service, sink = _service(port)

    payload = service.answer(
        _request("这个套装有几块电池？", variant_id="mini-standard")
    ).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.VARIANT_NOT_FOUND
    assert (port.product_calls, port.variant_calls, port.commerce_calls) == (0, 1, 0)
    _assert_identity_failure_trace(sink)


def test_variant_read_preserves_explicit_product_not_found_semantics() -> None:
    port = _ControlledShopifyPort(variants=_not_found(ToolErrorCode.PRODUCT_NOT_FOUND))
    service, sink = _service(port)

    payload = service.answer(
        _request(
            "这个套装有几块电池？",
            product_id="missing-product",
            variant_id="missing-variant",
        )
    ).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.PRODUCT_NOT_FOUND
    assert (port.product_calls, port.variant_calls, port.commerce_calls) == (0, 1, 0)
    _assert_identity_failure_trace(sink)


def test_product_fact_uses_only_shared_attributes_and_never_variant_ids() -> None:
    product = _product()
    port = _ControlledShopifyPort(products=_success([product]))
    service, _ = _service(port)

    payload = service.answer(_request("这款无人机的制造商是谁？")).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    assert payload.claims[0].fact is product.shared_attributes["manufacturer"]
    assert payload.evidence[0].fact == product.shared_attributes["manufacturer"]
    assert payload.evidence[0].observed_at == NOW
    assert payload.resolved_scope.variant_id is None
    assert payload.evidence[0].variant_id is None
    assert (port.product_calls, port.variant_calls, port.commerce_calls) == (1, 0, 0)


def _assert_identity_failure_trace(sink: InMemoryTraceSink) -> None:
    event_types = {event.event_type for event in sink.events}
    assert TraceEventType.FALLBACK_PRODUCED in event_types
    assert TraceEventType.PAGE_CONTEXT_RESOLVED not in event_types
    assert TraceEventType.EVIDENCE_ACCEPTED not in event_types
    assert TraceEventType.ANSWER_PRODUCED not in event_types
    assert {event.correlation_id for event in sink.events} == {"correlation-t05-unit"}
