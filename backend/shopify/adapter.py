"""Protocol-independent live Shopify read adapter for the Slice 10 pilot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any

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
from backend.shopify.fixture import CallClassification, ReadCallLedgerEntry
from backend.shopify.port import CommerceState, ShopifyReadPort
from backend.shopify.transport import (
    ShopifyReadTransport,
    ShopifyTransportFailure,
    ShopifyTransportResult,
)


class ShopifyAdapterStopReason(StrEnum):
    """Internal diagnostic reasons kept out of public ToolResult payloads."""

    CREDENTIAL_FAILURE = "CREDENTIAL_FAILURE"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_FOUND = "NOT_FOUND"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    MISSING_FIELD = "MISSING_FIELD"
    SHOPIFY_READ_CALL_LIMIT = "SHOPIFY_READ_CALL_LIMIT"


class _AdapterValidationError(ValueError):
    def __init__(self, reason: ShopifyAdapterStopReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class RealShopifyReadAdapter(ShopifyReadPort):
    """Read-only adapter with explicit scope guards and a safe read ledger."""

    def __init__(
        self,
        *,
        transport: ShopifyReadTransport,
        clock: Callable[[], datetime] | None = None,
        approved_variant_ids: Mapping[str, str] | None = None,
        approved_store_id: str | None = None,
        max_read_calls: int = 2,
        max_attempts: int = 1,
    ) -> None:
        if max_read_calls <= 0:
            raise ValueError("Shopify read-call budget must be positive")
        if max_attempts != 1:
            raise ValueError("Shopify adapter permits one attempt and no retries")
        self._transport = transport
        self._clock = clock or (lambda: datetime.now(UTC))
        self._approved_variant_ids = MappingProxyType(dict(approved_variant_ids or {}))
        self._approved_store_id = approved_store_id
        self._max_read_calls = max_read_calls
        self._call_ledger: list[ReadCallLedgerEntry] = []
        self._last_stop_reason: ShopifyAdapterStopReason | None = None

    @property
    def call_ledger(self) -> tuple[ReadCallLedgerEntry, ...]:
        return tuple(self._call_ledger)

    @property
    def write_call_count(self) -> int:
        return 0

    @property
    def last_stop_reason(self) -> ShopifyAdapterStopReason | None:
        return self._last_stop_reason

    def _begin_turn(self) -> None:
        """Reset the bounded read ledger at the start of one conversation turn.

        The adapter instance is intentionally reused by the runtime, while
        ``max_read_calls`` is a per-turn budget.  Keeping this hook private
        avoids expanding the Shopify port or public contract surface.
        """
        self._call_ledger.clear()
        self._last_stop_reason = None

    def get_products(
        self, *, store_id: str, product_id: str
    ) -> ToolResult[list[ProductRecord]]:
        self._begin_call()
        source = _product_source(store_id, product_id)
        if self._approved_store_id is not None and store_id != self._approved_store_id:
            return self._validation_error(
                source=source,
                reason=ShopifyAdapterStopReason.IDENTITY_MISMATCH,
                error_code=ToolErrorCode.PRODUCT_NOT_FOUND,
            )
        if self._read_budget_exhausted():
            return self._budget_error(source, ToolErrorCode.PRODUCT_NOT_FOUND)
        self._record_read(TraceOperation.GET_PRODUCTS, store_id, product_id)
        response = self._transport_result(
            lambda: self._transport.read_product(
                store_id=store_id,
                product_id=product_id,
            )
        )
        failure = self._transport_failure(response)
        if failure is not None:
            return self._error(source=source, failure=failure)
        try:
            assert response.payload is not None
            product = _product_payload(response.payload)
            normalized = _normalize_product(
                product,
                store_id=store_id,
                requested_product_id=product_id,
            )
            expected_variant_id = self._approved_variant_ids.get(product_id)
            if (
                expected_variant_id is not None
                and expected_variant_id not in normalized.variant_ids
            ):
                raise _AdapterValidationError(
                    ShopifyAdapterStopReason.IDENTITY_MISMATCH
                )
        except _AdapterValidationError as error:
            return self._validation_error(
                source=source,
                reason=error.reason,
                error_code=ToolErrorCode.PRODUCT_NOT_FOUND,
            )
        return self._success(data=[normalized], source=source)

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ) -> ToolResult[list[VariantRecord]]:
        self._begin_call()
        source = _product_source(store_id, product_id)
        if self._approved_store_id is not None and store_id != self._approved_store_id:
            return self._validation_error(
                source=source,
                reason=ShopifyAdapterStopReason.IDENTITY_MISMATCH,
                error_code=ToolErrorCode.PRODUCT_NOT_FOUND,
            )
        if variant_id is not None and self._approved_variant_ids.get(
            product_id
        ) not in {
            None,
            variant_id,
        }:
            return self._validation_error(
                source=source,
                reason=ShopifyAdapterStopReason.IDENTITY_MISMATCH,
                error_code=ToolErrorCode.VARIANT_NOT_FOUND,
            )
        if self._read_budget_exhausted():
            return self._budget_error(source, ToolErrorCode.VARIANT_NOT_FOUND)
        self._record_read(TraceOperation.GET_VARIANTS, store_id, product_id, variant_id)
        response = self._transport_result(
            lambda: self._transport.read_variants(
                store_id=store_id,
                product_id=product_id,
            )
        )
        failure = self._transport_failure(response)
        if failure is not None:
            return self._error(source=source, failure=failure)
        try:
            assert response.payload is not None
            records = _variants_payload(
                response.payload,
                store_id=store_id,
                requested_product_id=product_id,
            )
            expected_variant_id = self._approved_variant_ids.get(product_id)
            if expected_variant_id is not None and expected_variant_id not in {
                record.variant_id for record in records
            }:
                raise _AdapterValidationError(
                    ShopifyAdapterStopReason.IDENTITY_MISMATCH
                )
        except _AdapterValidationError as error:
            return self._validation_error(
                source=source,
                reason=error.reason,
                error_code=ToolErrorCode.VARIANT_NOT_FOUND,
            )
        if variant_id is not None:
            records = [record for record in records if record.variant_id == variant_id]
            if not records:
                return self._error(
                    source=_variant_source(store_id, product_id, variant_id),
                    failure=ShopifyTransportFailure.NOT_FOUND,
                )
        return self._success(data=records, source=source)

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult[CommerceState]:
        self._begin_call()
        source = _commerce_source(store_id, product_id, variant_id)
        if self._approved_store_id is not None and store_id != self._approved_store_id:
            return self._validation_error(
                source=source,
                reason=ShopifyAdapterStopReason.IDENTITY_MISMATCH,
                error_code=ToolErrorCode.VARIANT_NOT_FOUND,
            )
        if self._approved_variant_ids.get(product_id) not in {None, variant_id}:
            return self._validation_error(
                source=source,
                reason=ShopifyAdapterStopReason.IDENTITY_MISMATCH,
                error_code=ToolErrorCode.VARIANT_NOT_FOUND,
            )
        if self._read_budget_exhausted():
            return self._budget_error(source, ToolErrorCode.VARIANT_NOT_FOUND)
        self._record_read(
            TraceOperation.REFRESH_COMMERCE_STATE,
            store_id,
            product_id,
            variant_id,
        )
        response = self._transport_result(
            lambda: self._transport.read_commerce_state(
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
            )
        )
        response = self._commerce_response_with_product_fallback(
            response,
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
        )
        failure = self._transport_failure(response)
        if failure is not None:
            return self._error(source=source, failure=failure)
        observed_at = self._observed_at()
        try:
            assert response.payload is not None
            data, missing_fields = _commerce_payload(
                response.payload,
                product_id=product_id,
                variant_id=variant_id,
                source=source,
                observed_at=observed_at,
            )
        except _AdapterValidationError as error:
            return self._validation_error(
                source=source,
                reason=error.reason,
                error_code=ToolErrorCode.VARIANT_NOT_FOUND,
            )
        if missing_fields:
            self._last_stop_reason = ShopifyAdapterStopReason.MISSING_FIELD
            return ToolResult[CommerceState](
                status=ToolStatus.PARTIAL,
                data=data,
                source=source,
                observed_at=observed_at,
                error_code=ToolErrorCode.PARTIAL_RESULT,
                retryable=False,
                missing_fields=missing_fields,
            )
        return self._success(data=data, source=source, observed_at=observed_at)

    def _commerce_response_with_product_fallback(
        self,
        response: ShopifyTransportResult,
        *,
        store_id: str,
        product_id: str,
        variant_id: str,
    ) -> ShopifyTransportResult:
        """Use one same-product read for bounded commerce compatibility."""
        malformed_payload = response.failure is None and not _has_variant_payload(
            response.payload
        )
        if (
            response.failure
            not in {
                ShopifyTransportFailure.NOT_FOUND,
                ShopifyTransportFailure.MALFORMED_RESPONSE,
            }
            and not malformed_payload
        ):
            return response
        if self._read_budget_exhausted():
            return response
        self._record_read(TraceOperation.GET_PRODUCTS, store_id, product_id)
        product_response = self._transport_result(
            lambda: self._transport.read_product(
                store_id=store_id,
                product_id=product_id,
            )
        )
        if self._transport_failure(product_response) is not None:
            return response
        assert product_response.payload is not None
        variant = _product_variant_for_commerce(
            product_response.payload,
            product_id=product_id,
            variant_id=variant_id,
        )
        if variant is None:
            return response
        self._last_stop_reason = None
        return ShopifyTransportResult(
            payload={"variant": variant},
            http_status=product_response.http_status,
        )

    def _begin_call(self) -> None:
        self._last_stop_reason = None

    def _read_budget_exhausted(self) -> bool:
        return len(self._call_ledger) >= self._max_read_calls

    def _budget_error(self, source: str, error_code: ToolErrorCode):
        self._last_stop_reason = ShopifyAdapterStopReason.SHOPIFY_READ_CALL_LIMIT
        return ToolResult(
            status=ToolStatus.ERROR,
            source=source,
            observed_at=self._observed_at(),
            error_code=error_code,
            retryable=False,
        )

    def _record_read(
        self,
        operation: TraceOperation,
        store_id: str,
        product_id: str,
        variant_id: str | None = None,
    ) -> None:
        self._call_ledger.append(
            ReadCallLedgerEntry(
                sequence=len(self._call_ledger) + 1,
                operation=operation,
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                classification=CallClassification.READ,
            )
        )

    def _transport_result(self, operation: Callable[[], ShopifyTransportResult]):
        try:
            result = operation()
        except Exception:  # noqa: BLE001
            self._last_stop_reason = ShopifyAdapterStopReason.NETWORK_FAILURE
            return ShopifyTransportResult(failure=ShopifyTransportFailure.NETWORK_ERROR)
        if not isinstance(result, ShopifyTransportResult):
            self._last_stop_reason = ShopifyAdapterStopReason.MALFORMED_RESPONSE
            return ShopifyTransportResult(
                failure=ShopifyTransportFailure.MALFORMED_RESPONSE,
            )
        return result

    def _transport_failure(
        self, response: ShopifyTransportResult
    ) -> ShopifyTransportFailure | None:
        if response.failure is None:
            if not isinstance(response.payload, Mapping):
                self._last_stop_reason = ShopifyAdapterStopReason.MALFORMED_RESPONSE
                return ShopifyTransportFailure.MALFORMED_RESPONSE
            return None
        self._last_stop_reason = _stop_reason_for_failure(response.failure)
        return response.failure

    def _success(self, *, data, source: str, observed_at: datetime | None = None):
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=data,
            source=source,
            observed_at=observed_at or self._observed_at(),
            retryable=False,
        )

    def _error(
        self,
        *,
        source: str,
        failure: ShopifyTransportFailure,
        error_code: ToolErrorCode | None = None,
    ):
        self._last_stop_reason = _stop_reason_for_failure(failure)
        return ToolResult(
            status=ToolStatus.ERROR,
            source=source,
            observed_at=self._observed_at(),
            error_code=error_code or _tool_error_for_failure(failure, source),
            retryable=failure
            in {ShopifyTransportFailure.TIMEOUT, ShopifyTransportFailure.RATE_LIMITED},
        )

    def _validation_error(
        self,
        *,
        source: str,
        reason: ShopifyAdapterStopReason,
        error_code: ToolErrorCode | None = None,
    ):
        self._last_stop_reason = reason
        return ToolResult(
            status=ToolStatus.ERROR,
            source=source,
            observed_at=self._observed_at(),
            error_code=error_code or _tool_error_for_reason(reason, source),
            retryable=False,
        )

    def _observed_at(self) -> datetime:
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("Shopify adapter clock must be timezone-aware")
        return observed_at


def _product_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    product = payload.get("product")
    if not isinstance(product, Mapping):
        raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)
    return product


def _has_variant_payload(payload: Mapping[str, Any] | None) -> bool:
    return isinstance(payload, Mapping) and isinstance(payload.get("variant"), Mapping)


def _product_variant_for_commerce(
    payload: Mapping[str, Any], *, product_id: str, variant_id: str
) -> Mapping[str, Any] | None:
    """Select one exact Variant from a same-Product REST response."""
    try:
        product = _product_payload(payload)
        if _numeric_id(product.get("id"), "Product") != product_id:
            return None
    except _AdapterValidationError:
        return None
    raw_variants = product.get("variants")
    if not isinstance(raw_variants, list):
        return None
    matches: list[Mapping[str, Any]] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, Mapping):
            continue
        try:
            if _numeric_id(raw_variant.get("id"), "Variant") != variant_id:
                continue
            raw_product_id = raw_variant.get("product_id")
            if (
                raw_product_id is not None
                and _numeric_id(raw_product_id, "Product") != product_id
            ):
                continue
        except _AdapterValidationError:
            continue
        matches.append(raw_variant)
    return matches[0] if len(matches) == 1 else None


def _variants_payload(
    payload: Mapping[str, Any],
    *,
    store_id: str,
    requested_product_id: str,
) -> list[VariantRecord]:
    raw_variants = payload.get("variants")
    if not isinstance(raw_variants, list):
        raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)
    records: list[VariantRecord] = []
    seen: set[str] = set()
    for raw_variant in raw_variants:
        records.append(
            _normalize_variant(
                raw_variant,
                store_id=store_id,
                requested_product_id=requested_product_id,
                seen=seen,
            )
        )
    return records


def _normalize_product(
    product: Mapping[str, Any],
    *,
    store_id: str,
    requested_product_id: str,
) -> ProductRecord:
    observed_product_id = _numeric_id(product.get("id"), "Product")
    if observed_product_id != requested_product_id:
        raise _AdapterValidationError(ShopifyAdapterStopReason.IDENTITY_MISMATCH)
    title = product.get("title")
    raw_variants = product.get("variants")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(raw_variants, list)
    ):
        raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)
    seen: set[str] = set()
    variant_records = [
        _normalize_variant(
            raw_variant,
            store_id=store_id,
            requested_product_id=requested_product_id,
            seen=seen,
        )
        for raw_variant in raw_variants
    ]
    return ProductRecord(
        store_id=store_id,
        product_id=requested_product_id,
        display_title=title.strip(),
        shared_attributes={},
        variant_ids=[variant.variant_id for variant in variant_records],
    )


def _normalize_variant(
    raw_variant: Any,
    *,
    store_id: str,
    requested_product_id: str,
    seen: set[str],
) -> VariantRecord:
    if not isinstance(raw_variant, Mapping):
        raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)
    variant_id = _numeric_id(raw_variant.get("id"), "Variant")
    if variant_id in seen:
        raise _AdapterValidationError(ShopifyAdapterStopReason.IDENTITY_MISMATCH)
    seen.add(variant_id)
    raw_product_id = raw_variant.get("product_id")
    if (
        raw_product_id is not None
        and _numeric_id(raw_product_id, "Product") != requested_product_id
    ):
        raise _AdapterValidationError(ShopifyAdapterStopReason.IDENTITY_MISMATCH)
    title = raw_variant.get("title")
    if not isinstance(title, str) or not title.strip():
        raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)
    options = {
        f"option{index}": value.strip()
        for index in range(1, 4)
        if isinstance(value := raw_variant.get(f"option{index}"), str) and value.strip()
    }
    return VariantRecord(
        store_id=store_id,
        product_id=requested_product_id,
        variant_id=variant_id,
        display_label=title.strip(),
        options=options,
        variant_attributes={},
    )


def _commerce_payload(
    payload: Mapping[str, Any],
    *,
    product_id: str,
    variant_id: str,
    source: str,
    observed_at: datetime,
) -> tuple[CommerceState, list[str]]:
    variant = payload.get("variant")
    if not isinstance(variant, Mapping):
        raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)
    if _numeric_id(variant.get("id"), "Variant") != variant_id:
        raise _AdapterValidationError(ShopifyAdapterStopReason.IDENTITY_MISMATCH)
    raw_product_id = variant.get("product_id")
    if (
        raw_product_id is not None
        and _numeric_id(raw_product_id, "Product") != product_id
    ):
        raise _AdapterValidationError(ShopifyAdapterStopReason.IDENTITY_MISMATCH)

    data: CommerceState = {}
    missing: list[str] = []
    price = _numeric_value(variant.get("price"))
    if price is None:
        missing.append("price")
    else:
        data["price"] = _known(price, source, "price", observed_at, unit="CNY")

    inventory = _integer_value(variant.get("inventory_quantity"))
    if inventory is None:
        missing.append("inventory")
    else:
        data["inventory"] = _known(
            inventory, source, "inventory", observed_at, unit="unit"
        )

    available = variant.get("available_for_sale", variant.get("available"))
    if not isinstance(available, bool):
        available = inventory > 0 if inventory is not None else None
    if available is None:
        missing.append("availability")
    else:
        data["availability"] = _known(available, source, "availability", observed_at)
    if not data:
        raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)
    return data, missing


def _known(
    value: Any,
    source: str,
    field: str,
    observed_at: datetime,
    *,
    unit: str | None = None,
) -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=value,
        unit=unit,
        source_ref=f"{source}#commerce.{field}",
        observed_at=observed_at,
    )


def _numeric_id(raw: Any, kind: str) -> str:
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return str(raw)
    if isinstance(raw, str):
        prefixes = [f"gid://shopify/{kind}/"]
        if kind == "Variant":
            prefixes.append("gid://shopify/ProductVariant/")
        for prefix in prefixes:
            value = raw.removeprefix(prefix)
            if value.isdigit():
                return value
    raise _AdapterValidationError(ShopifyAdapterStopReason.MALFORMED_RESPONSE)


def _numeric_value(raw: Any) -> int | float | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not isfinite(value):
        return None
    return int(value) if value.is_integer() else value


def _integer_value(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw)
    return None


def _stop_reason_for_failure(
    failure: ShopifyTransportFailure,
) -> ShopifyAdapterStopReason:
    return {
        ShopifyTransportFailure.TIMEOUT: ShopifyAdapterStopReason.TIMEOUT,
        ShopifyTransportFailure.RATE_LIMITED: ShopifyAdapterStopReason.RATE_LIMITED,
        ShopifyTransportFailure.UNAUTHORIZED: ShopifyAdapterStopReason.UNAUTHORIZED,
        ShopifyTransportFailure.NOT_FOUND: ShopifyAdapterStopReason.NOT_FOUND,
        ShopifyTransportFailure.MALFORMED_RESPONSE: (
            ShopifyAdapterStopReason.MALFORMED_RESPONSE
        ),
        ShopifyTransportFailure.NETWORK_ERROR: ShopifyAdapterStopReason.NETWORK_FAILURE,
    }[failure]


def _tool_error_for_failure(
    failure: ShopifyTransportFailure,
    source: str,
) -> ToolErrorCode:
    if failure is ShopifyTransportFailure.TIMEOUT:
        return ToolErrorCode.TIMEOUT
    if failure is ShopifyTransportFailure.RATE_LIMITED:
        return ToolErrorCode.RATE_LIMITED
    if failure is ShopifyTransportFailure.UNAUTHORIZED:
        return ToolErrorCode.UNAUTHORIZED
    if failure is ShopifyTransportFailure.NOT_FOUND:
        return (
            ToolErrorCode.VARIANT_NOT_FOUND
            if "/variants/" in source
            else ToolErrorCode.PRODUCT_NOT_FOUND
        )
    return (
        ToolErrorCode.VARIANT_NOT_FOUND
        if "/variants/" in source
        else ToolErrorCode.PRODUCT_NOT_FOUND
    )


def _tool_error_for_reason(
    reason: ShopifyAdapterStopReason,
    source: str,
) -> ToolErrorCode:
    if reason is ShopifyAdapterStopReason.TIMEOUT:
        return ToolErrorCode.TIMEOUT
    if reason is ShopifyAdapterStopReason.RATE_LIMITED:
        return ToolErrorCode.RATE_LIMITED
    if reason in {
        ShopifyAdapterStopReason.CREDENTIAL_FAILURE,
        ShopifyAdapterStopReason.UNAUTHORIZED,
    }:
        return ToolErrorCode.UNAUTHORIZED
    return (
        ToolErrorCode.VARIANT_NOT_FOUND
        if "/variants/" in source
        else ToolErrorCode.PRODUCT_NOT_FOUND
    )


def _product_source(store_id: str, product_id: str) -> str:
    return f"shopify://{store_id}/products/{product_id}"


def _variant_source(store_id: str, product_id: str, variant_id: str) -> str:
    return f"{_product_source(store_id, product_id)}/variants/{variant_id}"


def _commerce_source(store_id: str, product_id: str, variant_id: str) -> str:
    return f"{_variant_source(store_id, product_id, variant_id)}/commerce"


__all__ = ["RealShopifyReadAdapter", "ShopifyAdapterStopReason"]
