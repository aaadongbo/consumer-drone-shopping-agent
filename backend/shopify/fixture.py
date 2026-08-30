"""Deterministic, network-free Shopify read adapter used as a CI test double."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from backend.common import (
    AttributeStatus,
    AttributeValue,
    ProductRecord,
    ToolErrorCode,
    ToolResult,
    ToolStatus,
    TraceOperation,
    VariantRecord,
)
from backend.shopify.port import SHOPIFY_READ_OPERATIONS, CommerceState

_FIXTURE_STORE_ID = "store-drone-cn"


class FixtureOutcome(StrEnum):
    """Small, deterministic result branches supported by the fixture."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    VARIANT_NOT_FOUND = "VARIANT_NOT_FOUND"


class CallClassification(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class ReadCallLedgerEntry:
    sequence: int
    operation: TraceOperation
    store_id: str
    product_id: str
    variant_id: str | None
    classification: CallClassification = CallClassification.READ


_ALLOWED_OUTCOMES = MappingProxyType(
    {
        TraceOperation.GET_PRODUCTS: frozenset(
            {
                FixtureOutcome.SUCCESS,
                FixtureOutcome.PARTIAL,
                FixtureOutcome.TIMEOUT,
                FixtureOutcome.RATE_LIMITED,
                FixtureOutcome.UNAUTHORIZED,
                FixtureOutcome.PRODUCT_NOT_FOUND,
            }
        ),
        TraceOperation.GET_VARIANTS: frozenset(FixtureOutcome),
        TraceOperation.REFRESH_COMMERCE_STATE: frozenset(FixtureOutcome),
    }
)

_ERROR_CODES = MappingProxyType(
    {
        FixtureOutcome.TIMEOUT: ToolErrorCode.TIMEOUT,
        FixtureOutcome.RATE_LIMITED: ToolErrorCode.RATE_LIMITED,
        FixtureOutcome.UNAUTHORIZED: ToolErrorCode.UNAUTHORIZED,
        FixtureOutcome.PRODUCT_NOT_FOUND: ToolErrorCode.PRODUCT_NOT_FOUND,
        FixtureOutcome.VARIANT_NOT_FOUND: ToolErrorCode.VARIANT_NOT_FOUND,
    }
)


class DeterministicShopifyFixture:
    """Read-only fixture with injected time, outcomes, and a safe call ledger."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        forced_outcomes: Mapping[TraceOperation, FixtureOutcome] | None = None,
    ) -> None:
        configured_outcomes = dict(forced_outcomes or {})
        for operation, outcome in configured_outcomes.items():
            if operation not in SHOPIFY_READ_OPERATIONS:
                raise ValueError("Fixture outcomes accept read operations only")
            if outcome not in _ALLOWED_OUTCOMES[operation]:
                raise ValueError(f"{outcome} is not valid for {operation}")

        self._clock = clock
        self._forced_outcomes = MappingProxyType(configured_outcomes)
        self._products = _build_products()
        self._variants = _build_variants()
        self._commerce_templates = _build_commerce_templates()
        self._call_ledger: list[ReadCallLedgerEntry] = []

    @property
    def call_ledger(self) -> tuple[ReadCallLedgerEntry, ...]:
        return tuple(self._call_ledger)

    @property
    def write_call_count(self) -> int:
        return sum(
            entry.classification is CallClassification.WRITE
            for entry in self._call_ledger
        )

    def get_products(
        self, *, store_id: str, product_id: str
    ) -> ToolResult[list[ProductRecord]]:
        operation = TraceOperation.GET_PRODUCTS
        self._record_read(operation, store_id, product_id)
        observed_at = self._observed_at()
        source = _product_source(store_id, product_id)
        product = self._products.get((store_id, product_id))
        outcome = self._forced_outcomes.get(operation, FixtureOutcome.SUCCESS)

        if outcome is not FixtureOutcome.SUCCESS:
            if outcome is FixtureOutcome.PARTIAL:
                if product is None:
                    return _error_result(
                        FixtureOutcome.PRODUCT_NOT_FOUND, source, observed_at
                    )
                return _partial_result(
                    data=[product.model_copy(deep=True)],
                    source=source,
                    observed_at=observed_at,
                    missing_fields=["shared_attributes.supported_app"],
                )
            return _error_result(outcome, source, observed_at)
        if product is None:
            return _error_result(FixtureOutcome.PRODUCT_NOT_FOUND, source, observed_at)
        return _success_result([product.model_copy(deep=True)], source, observed_at)

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ) -> ToolResult[list[VariantRecord]]:
        operation = TraceOperation.GET_VARIANTS
        self._record_read(operation, store_id, product_id, variant_id)
        observed_at = self._observed_at()
        source = _variant_source(store_id, product_id, variant_id)
        product = self._products.get((store_id, product_id))
        variants = [
            variant
            for (record_store, record_product, _), variant in self._variants.items()
            if record_store == store_id and record_product == product_id
        ]
        if variant_id is not None:
            variants = [
                variant for variant in variants if variant.variant_id == variant_id
            ]
        outcome = self._forced_outcomes.get(operation, FixtureOutcome.SUCCESS)

        if outcome is not FixtureOutcome.SUCCESS:
            if outcome is FixtureOutcome.PARTIAL:
                if product is None:
                    return _error_result(
                        FixtureOutcome.PRODUCT_NOT_FOUND, source, observed_at
                    )
                if not variants and variant_id is not None:
                    return _error_result(
                        FixtureOutcome.VARIANT_NOT_FOUND, source, observed_at
                    )
                return _partial_result(
                    data=[variant.model_copy(deep=True) for variant in variants],
                    source=source,
                    observed_at=observed_at,
                    missing_fields=["variant_attributes.remote_controller"],
                )
            return _error_result(outcome, source, observed_at)
        if product is None:
            return _error_result(FixtureOutcome.PRODUCT_NOT_FOUND, source, observed_at)
        if variant_id is not None and not variants:
            return _error_result(FixtureOutcome.VARIANT_NOT_FOUND, source, observed_at)
        return _success_result(
            [variant.model_copy(deep=True) for variant in variants],
            source,
            observed_at,
        )

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult[CommerceState]:
        operation = TraceOperation.REFRESH_COMMERCE_STATE
        self._record_read(operation, store_id, product_id, variant_id)
        observed_at = self._observed_at()
        source = _variant_source(store_id, product_id, variant_id)
        product = self._products.get((store_id, product_id))
        template = self._commerce_templates.get((store_id, product_id, variant_id))
        outcome = self._forced_outcomes.get(operation, FixtureOutcome.SUCCESS)

        if outcome is not FixtureOutcome.SUCCESS:
            if outcome is FixtureOutcome.PARTIAL:
                if product is None:
                    return _error_result(
                        FixtureOutcome.PRODUCT_NOT_FOUND, source, observed_at
                    )
                if template is None:
                    return _error_result(
                        FixtureOutcome.VARIANT_NOT_FOUND, source, observed_at
                    )
                partial = _observed_commerce(template, observed_at, source)
                del partial["availability"]
                return _partial_result(
                    data=partial,
                    source=source,
                    observed_at=observed_at,
                    missing_fields=["availability"],
                )
            return _error_result(outcome, source, observed_at)
        if product is None:
            return _error_result(FixtureOutcome.PRODUCT_NOT_FOUND, source, observed_at)
        if template is None:
            return _error_result(FixtureOutcome.VARIANT_NOT_FOUND, source, observed_at)
        return _success_result(
            _observed_commerce(template, observed_at, source), source, observed_at
        )

    def _record_read(
        self,
        operation: TraceOperation,
        store_id: str,
        product_id: str,
        variant_id: str | None = None,
    ) -> None:
        if operation not in SHOPIFY_READ_OPERATIONS:
            raise ValueError("Only allowlisted Shopify read operations may be recorded")
        self._call_ledger.append(
            ReadCallLedgerEntry(
                sequence=len(self._call_ledger) + 1,
                operation=operation,
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
            )
        )

    def _observed_at(self) -> datetime:
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("Fixture clock must return a timezone-aware datetime")
        return observed_at


def _success_result[FixtureDataT](
    data: FixtureDataT, source: str, observed_at: datetime
) -> ToolResult[FixtureDataT]:
    return ToolResult[FixtureDataT](
        status=ToolStatus.SUCCESS,
        data=data,
        source=source,
        observed_at=observed_at,
        retryable=False,
    )


def _partial_result[FixtureDataT](
    *,
    data: FixtureDataT,
    source: str,
    observed_at: datetime,
    missing_fields: list[str],
) -> ToolResult[FixtureDataT]:
    return ToolResult[FixtureDataT](
        status=ToolStatus.PARTIAL,
        data=data,
        source=source,
        observed_at=observed_at,
        error_code=ToolErrorCode.PARTIAL_RESULT,
        retryable=True,
        missing_fields=missing_fields,
    )


def _error_result(
    outcome: FixtureOutcome, source: str, observed_at: datetime
) -> ToolResult:
    error_code = _ERROR_CODES.get(outcome)
    if error_code is None:
        raise ValueError(f"{outcome} cannot produce an error result")
    return ToolResult(
        status=ToolStatus.ERROR,
        source=source,
        observed_at=observed_at,
        error_code=error_code,
        retryable=outcome in {FixtureOutcome.TIMEOUT, FixtureOutcome.RATE_LIMITED},
    )


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


def _build_products() -> dict[tuple[str, str], ProductRecord]:
    products = [
        ProductRecord(
            store_id=_FIXTURE_STORE_ID,
            product_id="drone-mini",
            display_title="Aero Mini",
            shared_attributes={
                "manufacturer": _known(
                    "Aero Labs",
                    "fixture://store-drone-cn/products/drone-mini#manufacturer",
                ),
                "camera_sensor": _known(
                    "1/1.3-inch CMOS",
                    "fixture://store-drone-cn/products/drone-mini#camera_sensor",
                ),
            },
            variant_ids=["mini-standard", "mini-explorer"],
        ),
        ProductRecord(
            store_id=_FIXTURE_STORE_ID,
            product_id="drone-cine",
            display_title="Aero Cine",
            shared_attributes={
                "manufacturer": _known(
                    "Aero Labs",
                    "fixture://store-drone-cn/products/drone-cine#manufacturer",
                ),
                "camera_sensor": _known(
                    "4/3 CMOS",
                    "fixture://store-drone-cn/products/drone-cine#camera_sensor",
                ),
            },
            variant_ids=["cine-standard"],
        ),
    ]
    return {(product.store_id, product.product_id): product for product in products}


def _build_variants() -> dict[tuple[str, str, str], VariantRecord]:
    variants = [
        VariantRecord(
            store_id=_FIXTURE_STORE_ID,
            product_id="drone-mini",
            variant_id="mini-standard",
            display_label="Standard Combo",
            options={"bundle": "standard", "color": "gray"},
            variant_attributes={
                "bundle_name": _known(
                    "Standard Combo",
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-standard#bundle_name",
                ),
                "battery_count": _known(
                    1,
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-standard#battery_count",
                    unit="battery",
                ),
                "takeoff_weight": _known(
                    249,
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-standard#takeoff_weight",
                    unit="g",
                ),
                "obstacle_sensing": _unknown(
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-standard#obstacle_sensing"
                ),
            },
        ),
        VariantRecord(
            store_id=_FIXTURE_STORE_ID,
            product_id="drone-mini",
            variant_id="mini-explorer",
            display_label="Explorer Combo",
            options={"bundle": "explorer", "color": "white"},
            variant_attributes={
                "bundle_name": _known(
                    "Explorer Combo",
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-explorer#bundle_name",
                ),
                "battery_count": _known(
                    3,
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-explorer#battery_count",
                    unit="battery",
                ),
                "takeoff_weight": _known(
                    253,
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-explorer#takeoff_weight",
                    unit="g",
                ),
                "obstacle_sensing": _known(
                    "three-direction",
                    "fixture://store-drone-cn/products/drone-mini/variants/mini-explorer#obstacle_sensing",
                ),
            },
        ),
        VariantRecord(
            store_id=_FIXTURE_STORE_ID,
            product_id="drone-cine",
            variant_id="cine-standard",
            display_label="Cine Standard",
            options={"bundle": "standard", "color": "black"},
            variant_attributes={
                "bundle_name": _known(
                    "Cine Standard",
                    "fixture://store-drone-cn/products/drone-cine/variants/cine-standard#bundle_name",
                ),
                "battery_count": _known(
                    1,
                    "fixture://store-drone-cn/products/drone-cine/variants/cine-standard#battery_count",
                    unit="battery",
                ),
                "takeoff_weight": _known(
                    895,
                    "fixture://store-drone-cn/products/drone-cine/variants/cine-standard#takeoff_weight",
                    unit="g",
                ),
            },
        ),
    ]
    return {
        (variant.store_id, variant.product_id, variant.variant_id): variant
        for variant in variants
    }


def _build_commerce_templates() -> dict[tuple[str, str, str], dict[str, object]]:
    return {
        (_FIXTURE_STORE_ID, "drone-mini", "mini-standard"): {
            "price": (2999, "CNY"),
            "inventory": (12, "unit"),
            "availability": (True, None),
        },
        (_FIXTURE_STORE_ID, "drone-mini", "mini-explorer"): {
            "price": (4399, "CNY"),
            "inventory": (0, "unit"),
            "availability": (False, None),
        },
        (_FIXTURE_STORE_ID, "drone-cine", "cine-standard"): {
            "price": (8999, "CNY"),
            "inventory": (4, "unit"),
            "availability": (True, None),
        },
    }


def _observed_commerce(
    template: Mapping[str, object], observed_at: datetime, source: str
) -> CommerceState:
    result: CommerceState = {}
    for field, raw_value in template.items():
        value, unit = raw_value
        result[field] = AttributeValue(
            status=AttributeStatus.KNOWN,
            value=value,
            unit=unit,
            source_ref=f"{source}#commerce.{field}",
            observed_at=observed_at,
        )
    return result


def _product_source(store_id: str, product_id: str) -> str:
    return f"fixture://{store_id}/products/{product_id}"


def _variant_source(store_id: str, product_id: str, variant_id: str | None) -> str:
    variant_component = variant_id if variant_id is not None else "*"
    return f"fixture://{store_id}/products/{product_id}/variants/{variant_component}"
