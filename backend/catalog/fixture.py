"""Minimal anonymous catalog and commerce data for Slice 2 validation."""

from dataclasses import dataclass
from datetime import datetime

from backend.common import (
    AttributeStatus,
    AttributeValue,
    ProductRecord,
    ToolResult,
    ToolStatus,
    VariantRecord,
)

type CommerceState = dict[str, AttributeValue]

PRIMARY_STORE_ID = "store-s02-alpha"
ISOLATION_STORE_ID = "store-s02-beta"

_EXPECTED_UNITS = {
    "battery_count": "battery",
    "takeoff_weight": "g",
    "price": "CNY",
    "inventory": "unit",
}


@dataclass(frozen=True, slots=True)
class VariantCommerceSnapshot:
    """One current commerce result with its complete owning identity."""

    store_id: str
    product_id: str
    variant_id: str
    result: ToolResult[CommerceState]


@dataclass(frozen=True, slots=True)
class CatalogFixtureSnapshot:
    """A deterministic store-scoped view of normalized fixture records."""

    store_id: str
    products: tuple[ProductRecord, ...]
    variants: tuple[VariantRecord, ...]
    commerce: tuple[VariantCommerceSnapshot, ...]


class DeterministicCatalogFixture:
    """Build fresh, replayable store views without network or external data."""

    def __init__(self, *, observed_at: datetime) -> None:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("Catalog fixture observed_at must be timezone-aware")
        self._observed_at = observed_at

    def load_store(self, *, store_id: str) -> CatalogFixtureSnapshot:
        """Return only records owned by ``store_id`` in deterministic order."""
        products = tuple(
            sorted(
                (
                    product
                    for product in _build_products()
                    if product.store_id == store_id
                ),
                key=lambda product: product.product_id,
            )
        )
        variants = tuple(
            sorted(
                (
                    variant
                    for variant in _build_variants()
                    if variant.store_id == store_id
                ),
                key=lambda variant: (variant.product_id, variant.variant_id),
            )
        )
        commerce = tuple(
            sorted(
                (
                    snapshot
                    for snapshot in _build_commerce(self._observed_at)
                    if snapshot.store_id == store_id
                ),
                key=lambda snapshot: (snapshot.product_id, snapshot.variant_id),
            )
        )
        snapshot = CatalogFixtureSnapshot(
            store_id=store_id,
            products=products,
            variants=variants,
            commerce=commerce,
        )
        _validate_snapshot(snapshot)
        return snapshot


def _known(
    value: object, source_ref: str, *, unit: str | None = None
) -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=value,
        unit=unit,
        source_ref=source_ref,
    )


def _unknown(source_ref: str) -> AttributeValue:
    return AttributeValue(status=AttributeStatus.UNKNOWN, source_ref=source_ref)


def _not_applicable(source_ref: str) -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.NOT_APPLICABLE,
        source_ref=source_ref,
    )


def _product_source(store_id: str, product_id: str) -> str:
    return f"fixture://{store_id}/products/{product_id}"


def _variant_source(store_id: str, product_id: str, variant_id: str) -> str:
    return f"{_product_source(store_id, product_id)}/variants/{variant_id}"


def _attribute(
    *,
    store_id: str,
    product_id: str,
    field: str,
    value: object | None = None,
    unit: str | None = None,
    status: AttributeStatus = AttributeStatus.KNOWN,
    variant_id: str | None = None,
) -> AttributeValue:
    source = _product_source(store_id, product_id)
    if variant_id is not None:
        source = _variant_source(store_id, product_id, variant_id)
    source_ref = f"{source}#{field}"
    if status is AttributeStatus.UNKNOWN:
        return _unknown(source_ref)
    if status is AttributeStatus.NOT_APPLICABLE:
        return _not_applicable(source_ref)
    return _known(value, source_ref, unit=unit)


def _build_products() -> list[ProductRecord]:
    rows = [
        (
            PRIMARY_STORE_ID,
            "drone-travel",
            "Northwind Travel",
            "travel",
            "4K",
            AttributeStatus.NOT_APPLICABLE,
            ["travel-lite", "travel-pack"],
        ),
        (
            PRIMARY_STORE_ID,
            "drone-cinema",
            "Northwind Cinema",
            "cinema",
            "5.1K",
            AttributeStatus.KNOWN,
            ["cinema-pro"],
        ),
        (
            PRIMARY_STORE_ID,
            "drone-survey",
            "Northwind Survey",
            "inspection",
            "4K",
            AttributeStatus.UNKNOWN,
            ["survey-base"],
        ),
        (
            ISOLATION_STORE_ID,
            "drone-travel",
            "Contoso Travel",
            "travel",
            "2.7K",
            AttributeStatus.NOT_APPLICABLE,
            ["travel-lite"],
        ),
    ]
    products = []
    for store_id, product_id, title, use_case, camera, lens_status, variants in rows:
        lens_value = lens_status is AttributeStatus.KNOWN
        products.append(
            ProductRecord(
                store_id=store_id,
                product_id=product_id,
                display_title=title,
                shared_attributes={
                    "use_case": _attribute(
                        store_id=store_id,
                        product_id=product_id,
                        field="use_case",
                        value=use_case,
                    ),
                    "camera_resolution": _attribute(
                        store_id=store_id,
                        product_id=product_id,
                        field="camera_resolution",
                        value=camera,
                    ),
                    "interchangeable_lens": _attribute(
                        store_id=store_id,
                        product_id=product_id,
                        field="interchangeable_lens",
                        value=lens_value,
                        status=lens_status,
                    ),
                },
                variant_ids=variants,
            )
        )
    return products


def _variant(
    *,
    store_id: str,
    product_id: str,
    variant_id: str,
    label: str,
    bundle: str,
    battery_count: int,
    takeoff_weight: int | None,
    obstacle_status: AttributeStatus,
    obstacle_value: str | None = None,
) -> VariantRecord:
    weight_status = (
        AttributeStatus.KNOWN if takeoff_weight is not None else AttributeStatus.UNKNOWN
    )
    return VariantRecord(
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        display_label=label,
        options={"bundle": bundle},
        variant_attributes={
            "battery_count": _attribute(
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                field="battery_count",
                value=battery_count,
                unit="battery",
            ),
            "takeoff_weight": _attribute(
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                field="takeoff_weight",
                value=takeoff_weight,
                unit="g",
                status=weight_status,
            ),
            "obstacle_sensing": _attribute(
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                field="obstacle_sensing",
                value=obstacle_value,
                status=obstacle_status,
            ),
        },
    )


def _build_variants() -> list[VariantRecord]:
    return [
        _variant(
            store_id=PRIMARY_STORE_ID,
            product_id="drone-travel",
            variant_id="travel-lite",
            label="Lite Combo",
            bundle="lite",
            battery_count=1,
            takeoff_weight=249,
            obstacle_status=AttributeStatus.UNKNOWN,
        ),
        _variant(
            store_id=PRIMARY_STORE_ID,
            product_id="drone-travel",
            variant_id="travel-pack",
            label="Travel Pack",
            bundle="travel",
            battery_count=3,
            takeoff_weight=253,
            obstacle_status=AttributeStatus.KNOWN,
            obstacle_value="three-direction",
        ),
        _variant(
            store_id=PRIMARY_STORE_ID,
            product_id="drone-cinema",
            variant_id="cinema-pro",
            label="Pro Kit",
            bundle="pro",
            battery_count=2,
            takeoff_weight=895,
            obstacle_status=AttributeStatus.KNOWN,
            obstacle_value="omnidirectional",
        ),
        _variant(
            store_id=PRIMARY_STORE_ID,
            product_id="drone-survey",
            variant_id="survey-base",
            label="Base Kit",
            bundle="base",
            battery_count=1,
            takeoff_weight=None,
            obstacle_status=AttributeStatus.NOT_APPLICABLE,
        ),
        _variant(
            store_id=ISOLATION_STORE_ID,
            product_id="drone-travel",
            variant_id="travel-lite",
            label="Regional Lite",
            bundle="regional",
            battery_count=2,
            takeoff_weight=310,
            obstacle_status=AttributeStatus.KNOWN,
            obstacle_value="forward",
        ),
    ]


def _commerce_result(
    *,
    store_id: str,
    product_id: str,
    variant_id: str,
    price: int,
    inventory: int,
    available: bool,
    observed_at: datetime,
) -> VariantCommerceSnapshot:
    source = f"{_variant_source(store_id, product_id, variant_id)}/commerce"
    data = {
        "price": AttributeValue(
            status=AttributeStatus.KNOWN,
            value=price,
            unit="CNY",
            source_ref=f"{source}#price",
            observed_at=observed_at,
        ),
        "inventory": AttributeValue(
            status=AttributeStatus.KNOWN,
            value=inventory,
            unit="unit",
            source_ref=f"{source}#inventory",
            observed_at=observed_at,
        ),
        "availability": AttributeValue(
            status=AttributeStatus.KNOWN,
            value=available,
            source_ref=f"{source}#availability",
            observed_at=observed_at,
        ),
    }
    return VariantCommerceSnapshot(
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        result=ToolResult[CommerceState](
            status=ToolStatus.SUCCESS,
            data=data,
            source=source,
            observed_at=observed_at,
            retryable=False,
        ),
    )


def _build_commerce(observed_at: datetime) -> list[VariantCommerceSnapshot]:
    rows = [
        (PRIMARY_STORE_ID, "drone-travel", "travel-lite", 2999, 12, True),
        (PRIMARY_STORE_ID, "drone-travel", "travel-pack", 4399, 0, False),
        (PRIMARY_STORE_ID, "drone-cinema", "cinema-pro", 8999, 4, True),
        (PRIMARY_STORE_ID, "drone-survey", "survey-base", 5799, 2, True),
        (ISOLATION_STORE_ID, "drone-travel", "travel-lite", 1999, 7, True),
    ]
    return [
        _commerce_result(
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
            price=price,
            inventory=inventory,
            available=available,
            observed_at=observed_at,
        )
        for store_id, product_id, variant_id, price, inventory, available in rows
    ]


def _validate_snapshot(snapshot: CatalogFixtureSnapshot) -> None:
    products = {product.product_id: product for product in snapshot.products}
    if len(products) != len(snapshot.products):
        raise ValueError("Catalog fixture contains duplicate product identity")

    variants = {
        (variant.product_id, variant.variant_id): variant
        for variant in snapshot.variants
    }
    if len(variants) != len(snapshot.variants):
        raise ValueError("Catalog fixture contains duplicate variant identity")

    commerce = {
        (entry.product_id, entry.variant_id): entry for entry in snapshot.commerce
    }
    if len(commerce) != len(snapshot.commerce):
        raise ValueError("Catalog fixture contains duplicate commerce identity")

    for product in snapshot.products:
        if product.store_id != snapshot.store_id:
            raise ValueError("Product crossed the requested store boundary")
        owned_ids = {
            variant.variant_id
            for variant in snapshot.variants
            if variant.product_id == product.product_id
        }
        if owned_ids != set(product.variant_ids):
            raise ValueError("Product variant references do not match owned variants")

    for key, variant in variants.items():
        if variant.store_id != snapshot.store_id or variant.product_id not in products:
            raise ValueError("Variant has no unique owning store/product")
        if key not in commerce:
            raise ValueError("Variant is missing its commerce snapshot")
        _validate_units(variant.variant_attributes)

    if set(commerce) != set(variants):
        raise ValueError("Commerce snapshot does not match catalog variants")
    for entry in snapshot.commerce:
        if entry.store_id != snapshot.store_id:
            raise ValueError("Commerce data crossed the requested store boundary")
        if entry.result.observed_at != _single_observed_at(entry):
            raise ValueError("Commerce observed_at was not propagated unchanged")
        if entry.result.data is None:
            raise ValueError("Commerce fixture requires typed data")
        _validate_units(entry.result.data)


def _single_observed_at(entry: VariantCommerceSnapshot) -> datetime:
    """Return the single observation shared by every fact in one result."""
    if entry.result.data is None:
        raise ValueError("Commerce fixture requires typed data")
    observations = {fact.observed_at for fact in entry.result.data.values()}
    if len(observations) != 1:
        raise ValueError("Commerce facts must share one observed_at")
    observed_at = observations.pop()
    if observed_at is None:
        raise ValueError("Commerce facts require observed_at")
    return observed_at


def _validate_units(attributes: dict[str, AttributeValue]) -> None:
    for field, expected_unit in _EXPECTED_UNITS.items():
        fact = attributes.get(field)
        if fact is not None and fact.status is AttributeStatus.KNOWN:
            if fact.unit != expected_unit:
                raise ValueError(f"{field} must use {expected_unit}")
