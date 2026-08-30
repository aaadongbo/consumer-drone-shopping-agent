"""Contract coverage for the protocol-independent Shopify read boundary."""

import inspect
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter

from backend.common import (
    AttributeValue,
    ProductRecord,
    ToolResult,
    ToolStatus,
    TraceOperation,
    VariantRecord,
)
from backend.shopify import (
    SHOPIFY_READ_OPERATIONS,
    CallClassification,
    DeterministicShopifyFixture,
    FixtureOutcome,
    ShopifyReadPort,
)

pytestmark = pytest.mark.contract

FIXED_TIME = datetime(2026, 8, 30, 10, 30, tzinfo=UTC)
STORE_ID = "store-drone-cn"
APPROVED_METHODS = {
    "get_products",
    "get_variants",
    "refresh_commerce_state",
}


def fixture(
    operation: TraceOperation | None = None,
    outcome: FixtureOutcome = FixtureOutcome.SUCCESS,
) -> DeterministicShopifyFixture:
    forced = {} if operation is None else {operation: outcome}
    return DeterministicShopifyFixture(
        clock=lambda: FIXED_TIME,
        forced_outcomes=forced,
    )


def test_port_public_method_surface_is_exactly_the_approved_reads() -> None:
    methods = {
        name
        for name, member in inspect.getmembers(ShopifyReadPort, inspect.isfunction)
        if not name.startswith("_")
    }

    assert methods == APPROVED_METHODS


def test_port_and_adapter_have_no_write_or_generic_dispatcher_surface() -> None:
    prohibited = {
        "create",
        "update",
        "delete",
        "mutate",
        "mutation",
        "cart",
        "order",
        "customer",
        "inventory",
        "execute",
        "invoke",
        "dispatch",
        "operation",
    }

    for boundary in (ShopifyReadPort, DeterministicShopifyFixture):
        public_names = {
            name.lower() for name in dir(boundary) if not name.startswith("_")
        }
        assert not any(
            token in name
            for name in public_names
            for token in prohibited
            if name not in APPROVED_METHODS
        )


def test_existing_trace_operation_is_the_single_exact_read_allowlist() -> None:
    assert SHOPIFY_READ_OPERATIONS == {
        TraceOperation.GET_PRODUCTS,
        TraceOperation.GET_VARIANTS,
        TraceOperation.REFRESH_COMMERCE_STATE,
    }


@pytest.mark.parametrize(
    "probe",
    [
        "update_inventory",
        "create_cart",
        "delete_product",
        "arbitrary_graphql_mutation",
        "unknown_operation",
    ],
)
def test_unknown_and_write_operation_probes_are_rejected_without_ledger_pollution(
    probe: str,
) -> None:
    adapter = fixture()

    with pytest.raises(ValueError):
        TraceOperation(probe)

    assert adapter.call_ledger == ()
    assert adapter.write_call_count == 0


def test_actual_adapter_calls_create_only_safe_read_ledger_entries() -> None:
    adapter = fixture()

    adapter.get_products(store_id=STORE_ID, product_id="drone-mini")
    adapter.get_variants(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-standard",
    )
    adapter.refresh_commerce_state(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-standard",
    )

    assert [entry.sequence for entry in adapter.call_ledger] == [1, 2, 3]
    assert {entry.operation for entry in adapter.call_ledger} == (
        SHOPIFY_READ_OPERATIONS
    )
    assert {entry.classification for entry in adapter.call_ledger} == {
        CallClassification.READ
    }
    assert adapter.write_call_count == 0
    for entry in adapter.call_ledger:
        assert entry.store_id == STORE_ID
        assert entry.product_id == "drone-mini"
        assert not hasattr(entry, "request")
        assert not hasattr(entry, "response")
        assert not hasattr(entry, "token")
        assert not hasattr(entry, "headers")
        assert not hasattr(entry, "credentials")


def test_ledger_view_is_immutable_and_cannot_be_used_to_forge_calls() -> None:
    adapter = fixture()
    adapter.get_products(store_id=STORE_ID, product_id="drone-mini")

    ledger = adapter.call_ledger

    assert isinstance(ledger, tuple)
    with pytest.raises(AttributeError):
        ledger.append(ledger[0])  # type: ignore[attr-defined]
    assert len(adapter.call_ledger) == 1
    assert adapter.write_call_count == 0


def test_success_results_validate_against_existing_public_contracts() -> None:
    adapter = fixture()
    products = adapter.get_products(store_id=STORE_ID, product_id="drone-mini")
    variants = adapter.get_variants(store_id=STORE_ID, product_id="drone-mini")
    commerce = adapter.refresh_commerce_state(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-standard",
    )

    product_contract = TypeAdapter(ToolResult[list[ProductRecord]])
    variant_contract = TypeAdapter(ToolResult[list[VariantRecord]])
    commerce_contract = TypeAdapter(ToolResult[dict[str, AttributeValue]])

    assert product_contract.validate_json(products.to_wire_json()) == products
    assert variant_contract.validate_json(variants.to_wire_json()) == variants
    assert commerce_contract.validate_json(commerce.to_wire_json()) == commerce


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (FixtureOutcome.SUCCESS, ToolStatus.SUCCESS),
        (FixtureOutcome.PARTIAL, ToolStatus.PARTIAL),
        (FixtureOutcome.TIMEOUT, ToolStatus.ERROR),
        (FixtureOutcome.RATE_LIMITED, ToolStatus.ERROR),
        (FixtureOutcome.UNAUTHORIZED, ToolStatus.ERROR),
        (FixtureOutcome.PRODUCT_NOT_FOUND, ToolStatus.ERROR),
        (FixtureOutcome.VARIANT_NOT_FOUND, ToolStatus.ERROR),
    ],
)
def test_every_failure_injection_branch_still_uses_public_tool_result_contract(
    outcome: FixtureOutcome, expected_status: ToolStatus
) -> None:
    operation = TraceOperation.REFRESH_COMMERCE_STATE
    adapter = fixture(operation, outcome)
    result = adapter.refresh_commerce_state(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-standard",
    )

    restored = TypeAdapter(ToolResult[dict[str, AttributeValue]]).validate_json(
        result.to_wire_json()
    )

    assert restored == result
    assert result.status is expected_status
    assert result.observed_at == FIXED_TIME
    assert adapter.write_call_count == 0


def test_failure_configuration_rejects_invalid_operation_outcome_pair() -> None:
    with pytest.raises(ValueError, match="not valid"):
        fixture(TraceOperation.GET_PRODUCTS, FixtureOutcome.VARIANT_NOT_FOUND)
