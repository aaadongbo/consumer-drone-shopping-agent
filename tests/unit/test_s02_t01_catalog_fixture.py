"""S02-T01 data validation for the synthetic catalog/commerce baseline."""

import json
from datetime import UTC, datetime

import pytest

from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import ISOLATION_STORE_ID, PRIMARY_STORE_ID
from backend.common import AttributeStatus, ToolStatus

pytestmark = pytest.mark.unit

OBSERVED_AT = datetime(2026, 8, 31, 9, 15, tzinfo=UTC)


def load(store_id: str = PRIMARY_STORE_ID):
    return DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=store_id
    )


def test_fixture_load_is_deterministic_and_returns_fresh_records() -> None:
    first = load()
    second = load()

    assert first == second
    assert [product.product_id for product in first.products] == [
        "drone-cinema",
        "drone-survey",
        "drone-travel",
    ]
    assert [(variant.product_id, variant.variant_id) for variant in first.variants] == [
        ("drone-cinema", "cinema-pro"),
        ("drone-survey", "survey-base"),
        ("drone-travel", "travel-lite"),
        ("drone-travel", "travel-pack"),
    ]

    first.products[0].variant_ids.append("polluted")
    assert "polluted" not in second.products[0].variant_ids


def test_every_variant_has_one_explicit_store_product_owner() -> None:
    snapshot = load()
    products = {product.product_id: product for product in snapshot.products}

    for variant in snapshot.variants:
        assert variant.store_id == snapshot.store_id
        assert variant.product_id in products
        assert variant.variant_id in products[variant.product_id].variant_ids

    assert len(
        {(variant.product_id, variant.variant_id) for variant in snapshot.variants}
    ) == len(snapshot.variants)
    assert {(entry.product_id, entry.variant_id) for entry in snapshot.commerce} == {
        (variant.product_id, variant.variant_id) for variant in snapshot.variants
    }


def test_variant_values_stay_separate_and_dynamic_facts_stay_out_of_catalog() -> None:
    snapshot = load()
    variants = {
        (variant.product_id, variant.variant_id): variant
        for variant in snapshot.variants
    }
    commerce = {
        (entry.product_id, entry.variant_id): entry.result.data
        for entry in snapshot.commerce
    }
    lite = variants[("drone-travel", "travel-lite")].variant_attributes
    travel_pack = variants[("drone-travel", "travel-pack")].variant_attributes
    cinema = variants[("drone-cinema", "cinema-pro")].variant_attributes

    assert (lite["battery_count"].value, lite["takeoff_weight"].value) == (1, 249)
    assert (
        travel_pack["battery_count"].value,
        travel_pack["takeoff_weight"].value,
    ) == (
        3,
        253,
    )
    assert (cinema["battery_count"].value, cinema["takeoff_weight"].value) == (
        2,
        895,
    )
    assert commerce[("drone-travel", "travel-lite")]["price"].value == 2999
    assert commerce[("drone-travel", "travel-pack")]["price"].value == 4399
    assert commerce[("drone-cinema", "cinema-pro")]["price"].value == 8999
    for variant in snapshot.variants:
        assert not {"price", "inventory", "availability"} & set(
            variant.variant_attributes
        )


def test_known_unknown_and_not_applicable_states_are_preserved() -> None:
    snapshot = load()
    variants = {variant.variant_id: variant for variant in snapshot.variants}
    products = {product.product_id: product for product in snapshot.products}

    assert (
        variants["travel-lite"].variant_attributes["obstacle_sensing"].status
        is AttributeStatus.UNKNOWN
    )
    unknown_weight = variants["survey-base"].variant_attributes["takeoff_weight"]
    assert unknown_weight.status is AttributeStatus.UNKNOWN
    assert unknown_weight.value is None
    not_applicable = variants["survey-base"].variant_attributes["obstacle_sensing"]
    assert not_applicable.status is AttributeStatus.NOT_APPLICABLE
    assert not_applicable.value is None
    assert (
        products["drone-travel"].shared_attributes["interchangeable_lens"].status
        is AttributeStatus.NOT_APPLICABLE
    )


def test_constraint_units_and_value_types_are_explicit() -> None:
    snapshot = load()

    for variant in snapshot.variants:
        battery = variant.variant_attributes["battery_count"]
        weight = variant.variant_attributes["takeoff_weight"]
        assert battery.unit == "battery"
        assert isinstance(battery.value, int)
        if weight.status is AttributeStatus.KNOWN:
            assert weight.unit == "g"
            assert isinstance(weight.value, int)

    for entry in snapshot.commerce:
        assert entry.result.data is not None
        price = entry.result.data["price"]
        inventory = entry.result.data["inventory"]
        availability = entry.result.data["availability"]
        assert price.unit == "CNY" and isinstance(price.value, int)
        assert inventory.unit == "unit" and isinstance(inventory.value, int)
        assert availability.unit is None and isinstance(availability.value, bool)


def test_commerce_snapshot_has_current_availability_and_exact_observed_at() -> None:
    snapshot = load()
    commerce = {entry.variant_id: entry.result for entry in snapshot.commerce}

    assert commerce["travel-lite"].data is not None
    assert commerce["travel-pack"].data is not None
    assert commerce["travel-lite"].data["availability"].value is True
    assert commerce["travel-pack"].data["availability"].value is False
    assert commerce["travel-lite"].data["inventory"].value == 12
    assert commerce["travel-pack"].data["inventory"].value == 0
    for result in commerce.values():
        assert result.status is ToolStatus.SUCCESS
        assert result.observed_at == OBSERVED_AT
        assert result.data is not None
        assert {fact.observed_at for fact in result.data.values()} == {OBSERVED_AT}
        assert all(
            fact.source_ref.startswith(result.source) for fact in result.data.values()
        )


def test_store_views_are_isolated_even_when_product_and_variant_ids_overlap() -> None:
    primary = load(PRIMARY_STORE_ID)
    isolated = load(ISOLATION_STORE_ID)

    assert {record.store_id for record in primary.products + primary.variants} == {
        PRIMARY_STORE_ID
    }
    assert {record.store_id for record in isolated.products + isolated.variants} == {
        ISOLATION_STORE_ID
    }
    assert primary.products[-1].product_id == isolated.products[0].product_id
    primary_variant = next(
        variant for variant in primary.variants if variant.variant_id == "travel-lite"
    )
    isolated_variant = isolated.variants[0]
    assert primary_variant.variant_id == isolated_variant.variant_id
    assert primary_variant.variant_attributes["takeoff_weight"].value == 249
    assert isolated_variant.variant_attributes["takeoff_weight"].value == 310
    primary_price = next(
        entry.result.data["price"].value
        for entry in primary.commerce
        if entry.variant_id == "travel-lite" and entry.result.data is not None
    )
    isolated_price = isolated.commerce[0].result.data
    assert isolated_price is not None
    assert primary_price == 2999
    assert isolated_price["price"].value == 1999
    assert load("store-not-present").products == ()


def test_fixture_contains_each_required_future_eligibility_case() -> None:
    snapshot = load()
    commerce = {entry.variant_id: entry.result.data for entry in snapshot.commerce}
    variants = {variant.variant_id: variant for variant in snapshot.variants}

    assert commerce["travel-lite"]["availability"].value is True
    assert commerce["travel-pack"]["availability"].value is False
    assert (
        variants["survey-base"].variant_attributes["takeoff_weight"].status
        is AttributeStatus.UNKNOWN
    )
    assert len({variant.product_id for variant in snapshot.variants}) >= 2


def test_serialized_fixture_contains_no_secret_or_customer_payload_fields() -> None:
    snapshot = load()
    wire = json.dumps(
        {
            "products": [record.to_wire() for record in snapshot.products],
            "variants": [record.to_wire() for record in snapshot.variants],
            "commerce": [entry.result.to_wire() for entry in snapshot.commerce],
        }
    ).lower()

    prohibited = {
        "authorization",
        "credential",
        "customer",
        "header",
        "order",
        "password",
        "secret",
        "token",
    }
    assert not any(field in wire for field in prohibited)
    assert "shopify" not in wire


def test_naive_observation_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DeterministicCatalogFixture(observed_at=datetime(2026, 8, 31, 9, 15))
