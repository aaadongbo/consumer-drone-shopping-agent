"""Unit coverage for deterministic Shopify fixture data and lookup behavior."""

from datetime import UTC, datetime

import pytest

from backend.common import AttributeStatus, ToolErrorCode, ToolStatus, TraceOperation
from backend.shopify import DeterministicShopifyFixture, FixtureOutcome

pytestmark = pytest.mark.unit

FIXED_TIME = datetime(2026, 8, 30, 10, 30, tzinfo=UTC)
STORE_ID = "store-drone-cn"


def fixture(
    operation: TraceOperation | None = None,
    outcome: FixtureOutcome = FixtureOutcome.SUCCESS,
) -> DeterministicShopifyFixture:
    forced = {} if operation is None else {operation: outcome}
    return DeterministicShopifyFixture(
        clock=lambda: FIXED_TIME,
        forced_outcomes=forced,
    )


def test_product_lookup_keeps_multiple_products_distinct() -> None:
    adapter = fixture()

    mini = adapter.get_products(store_id=STORE_ID, product_id="drone-mini")
    cine = adapter.get_products(store_id=STORE_ID, product_id="drone-cine")

    assert mini.status is ToolStatus.SUCCESS
    assert cine.status is ToolStatus.SUCCESS
    assert [product.product_id for product in mini.data or []] == ["drone-mini"]
    assert [product.product_id for product in cine.data or []] == ["drone-cine"]
    assert mini.data != cine.data


def test_product_records_contain_only_shared_attributes_and_identity_references() -> (
    None
):
    result = fixture().get_products(store_id=STORE_ID, product_id="drone-mini")
    assert result.data is not None
    product = result.data[0]

    assert set(product.shared_attributes) == {"manufacturer", "camera_sensor"}
    assert product.variant_ids == ["mini-standard", "mini-explorer"]
    assert (
        not {
            "price",
            "inventory",
            "availability",
            "bundle_name",
            "battery_count",
            "takeoff_weight",
            "obstacle_sensing",
        }
        & product.shared_attributes.keys()
    )


@pytest.mark.parametrize("outcome", [FixtureOutcome.SUCCESS, FixtureOutcome.PARTIAL])
def test_product_result_nested_mutation_does_not_pollute_later_lookup(
    outcome: FixtureOutcome,
) -> None:
    operation = TraceOperation.GET_PRODUCTS
    adapter = fixture(operation, outcome)
    first = adapter.get_products(store_id=STORE_ID, product_id="drone-mini")
    assert first.data is not None

    first.data[0].variant_ids.append("polluted-variant")
    first.data[0].shared_attributes.clear()
    second = adapter.get_products(store_id=STORE_ID, product_id="drone-mini")

    assert second.data is not None
    assert second.data[0].variant_ids == ["mini-standard", "mini-explorer"]
    manufacturer = second.data[0].shared_attributes["manufacturer"]
    assert manufacturer.value == "Aero Labs"
    assert manufacturer.source_ref.endswith("#manufacturer")


def test_variant_lookup_returns_only_owned_variants_without_defaulting() -> None:
    adapter = fixture()

    all_variants = adapter.get_variants(store_id=STORE_ID, product_id="drone-mini")
    selected = adapter.get_variants(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-explorer",
    )
    missing = adapter.get_variants(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="missing-variant",
    )

    assert all_variants.data is not None
    assert {variant.variant_id for variant in all_variants.data} == {
        "mini-standard",
        "mini-explorer",
    }
    assert selected.data is not None
    assert [variant.variant_id for variant in selected.data] == ["mini-explorer"]
    assert missing.status is ToolStatus.ERROR
    assert missing.error_code is ToolErrorCode.VARIANT_NOT_FOUND
    assert missing.data is None


def test_foreign_variant_does_not_cross_product_or_store_boundaries() -> None:
    adapter = fixture()

    foreign_product = adapter.get_variants(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="cine-standard",
    )
    foreign_store = adapter.get_variants(
        store_id="another-store",
        product_id="drone-mini",
        variant_id="mini-standard",
    )

    assert foreign_product.error_code is ToolErrorCode.VARIANT_NOT_FOUND
    assert foreign_store.error_code is ToolErrorCode.PRODUCT_NOT_FOUND
    assert foreign_product.data is None
    assert foreign_store.data is None


def test_variant_specific_known_unknown_and_bundle_values_remain_separate() -> None:
    result = fixture().get_variants(store_id=STORE_ID, product_id="drone-mini")
    assert result.data is not None
    variants = {variant.variant_id: variant for variant in result.data}
    standard = variants["mini-standard"].variant_attributes
    explorer = variants["mini-explorer"].variant_attributes

    assert standard["battery_count"].value == 1
    assert explorer["battery_count"].value == 3
    assert standard["bundle_name"].value == "Standard Combo"
    assert explorer["bundle_name"].value == "Explorer Combo"
    assert standard["takeoff_weight"].value == 249
    assert explorer["takeoff_weight"].value == 253
    assert standard["obstacle_sensing"].status is AttributeStatus.UNKNOWN
    assert standard["obstacle_sensing"].value is None
    assert explorer["obstacle_sensing"].status is AttributeStatus.KNOWN


@pytest.mark.parametrize("outcome", [FixtureOutcome.SUCCESS, FixtureOutcome.PARTIAL])
def test_variant_result_nested_mutation_does_not_pollute_later_lookup(
    outcome: FixtureOutcome,
) -> None:
    operation = TraceOperation.GET_VARIANTS
    adapter = fixture(operation, outcome)
    scope = {
        "store_id": STORE_ID,
        "product_id": "drone-mini",
        "variant_id": "mini-standard",
    }
    first = adapter.get_variants(**scope)
    assert first.data is not None

    first.data[0].options["bundle"] = "polluted"
    first.data[0].variant_attributes.clear()
    second = adapter.get_variants(**scope)

    assert second.data is not None
    assert second.data[0].options == {"bundle": "standard", "color": "gray"}
    unknown = second.data[0].variant_attributes["obstacle_sensing"]
    assert unknown.status is AttributeStatus.UNKNOWN
    assert unknown.value is None
    assert unknown.source_ref.endswith("#obstacle_sensing")


def test_dynamic_commerce_is_variant_scoped_and_not_stored_on_variant_record() -> None:
    adapter = fixture()

    standard = adapter.refresh_commerce_state(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-standard",
    )
    explorer = adapter.refresh_commerce_state(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-explorer",
    )
    variants = adapter.get_variants(store_id=STORE_ID, product_id="drone-mini")

    assert standard.data is not None
    assert explorer.data is not None
    assert standard.data["price"].value == 2999
    assert explorer.data["price"].value == 4399
    assert standard.data["inventory"].value == 12
    assert explorer.data["inventory"].value == 0
    assert standard.data["availability"].value is True
    assert explorer.data["availability"].value is False
    assert variants.data is not None
    for variant in variants.data:
        assert not {"price", "inventory", "availability"} & (
            variant.variant_attributes.keys()
        )


def test_fixed_clock_propagates_to_result_and_every_dynamic_attribute() -> None:
    result = fixture().refresh_commerce_state(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="mini-standard",
    )

    assert result.observed_at == FIXED_TIME
    assert result.data is not None
    assert {fact.observed_at for fact in result.data.values()} == {FIXED_TIME}


def test_naive_clock_is_rejected_instead_of_creating_uncontrolled_freshness() -> None:
    adapter = DeterministicShopifyFixture(clock=lambda: datetime(2026, 8, 30, 10, 30))

    with pytest.raises(ValueError, match="timezone-aware"):
        adapter.get_products(store_id=STORE_ID, product_id="drone-mini")


@pytest.mark.parametrize(
    ("operation", "outcome", "expected_code", "retryable"),
    [
        (
            TraceOperation.GET_PRODUCTS,
            FixtureOutcome.TIMEOUT,
            ToolErrorCode.TIMEOUT,
            True,
        ),
        (
            TraceOperation.GET_PRODUCTS,
            FixtureOutcome.RATE_LIMITED,
            ToolErrorCode.RATE_LIMITED,
            True,
        ),
        (
            TraceOperation.GET_PRODUCTS,
            FixtureOutcome.UNAUTHORIZED,
            ToolErrorCode.UNAUTHORIZED,
            False,
        ),
        (
            TraceOperation.GET_PRODUCTS,
            FixtureOutcome.PRODUCT_NOT_FOUND,
            ToolErrorCode.PRODUCT_NOT_FOUND,
            False,
        ),
        (
            TraceOperation.GET_VARIANTS,
            FixtureOutcome.VARIANT_NOT_FOUND,
            ToolErrorCode.VARIANT_NOT_FOUND,
            False,
        ),
    ],
)
def test_failure_injection_returns_distinguishable_error_results(
    operation: TraceOperation,
    outcome: FixtureOutcome,
    expected_code: ToolErrorCode,
    retryable: bool,
) -> None:
    adapter = fixture(operation, outcome)

    if operation is TraceOperation.GET_PRODUCTS:
        result = adapter.get_products(store_id=STORE_ID, product_id="drone-mini")
    else:
        result = adapter.get_variants(
            store_id=STORE_ID,
            product_id="drone-mini",
            variant_id="mini-standard",
        )

    assert result.status is ToolStatus.ERROR
    assert result.error_code is expected_code
    assert result.retryable is retryable
    assert result.data is None
    assert result.observed_at == FIXED_TIME


def test_missing_product_and_variant_are_natural_distinguishable_results() -> None:
    adapter = fixture()

    product = adapter.get_products(store_id=STORE_ID, product_id="missing")
    variant = adapter.refresh_commerce_state(
        store_id=STORE_ID,
        product_id="drone-mini",
        variant_id="missing",
    )

    assert product.error_code is ToolErrorCode.PRODUCT_NOT_FOUND
    assert variant.error_code is ToolErrorCode.VARIANT_NOT_FOUND


@pytest.mark.parametrize(
    "operation",
    [
        TraceOperation.GET_PRODUCTS,
        TraceOperation.GET_VARIANTS,
        TraceOperation.REFRESH_COMMERCE_STATE,
    ],
)
def test_partial_injection_contains_typed_data_and_explicit_missing_fields(
    operation: TraceOperation,
) -> None:
    adapter = fixture(operation, FixtureOutcome.PARTIAL)

    if operation is TraceOperation.GET_PRODUCTS:
        result = adapter.get_products(store_id=STORE_ID, product_id="drone-mini")
    elif operation is TraceOperation.GET_VARIANTS:
        result = adapter.get_variants(
            store_id=STORE_ID,
            product_id="drone-mini",
            variant_id="mini-standard",
        )
    else:
        result = adapter.refresh_commerce_state(
            store_id=STORE_ID,
            product_id="drone-mini",
            variant_id="mini-standard",
        )

    assert result.status is ToolStatus.PARTIAL
    assert result.error_code is ToolErrorCode.PARTIAL_RESULT
    assert result.data is not None
    assert result.missing_fields
    assert result.retryable is True
