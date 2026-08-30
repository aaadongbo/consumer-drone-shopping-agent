"""Typed read capabilities required by the Slice 1 Shopify boundary."""

from typing import Protocol

from backend.common import (
    AttributeValue,
    ProductRecord,
    ToolResult,
    TraceOperation,
    VariantRecord,
)

type CommerceState = dict[str, AttributeValue]

SHOPIFY_READ_OPERATIONS = frozenset(
    {
        TraceOperation.GET_PRODUCTS,
        TraceOperation.GET_VARIANTS,
        TraceOperation.REFRESH_COMMERCE_STATE,
    }
)


class ShopifyReadPort(Protocol):
    """The complete read-only Shopify capability surface for Slice 1."""

    def get_products(
        self, *, store_id: str, product_id: str
    ) -> ToolResult[list[ProductRecord]]:
        """Read one explicitly scoped product without searching."""
        ...

    def get_variants(
        self, *, store_id: str, product_id: str, variant_id: str | None = None
    ) -> ToolResult[list[VariantRecord]]:
        """Read all variants in a product or one explicitly scoped variant."""
        ...

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult[CommerceState]:
        """Read current dynamic facts for one explicit variant scope."""
        ...
