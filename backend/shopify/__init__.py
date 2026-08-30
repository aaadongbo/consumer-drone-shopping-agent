"""Protocol-independent, read-only Shopify boundary for Slice 1."""

from backend.shopify.fixture import (
    CallClassification,
    DeterministicShopifyFixture,
    FixtureOutcome,
    ReadCallLedgerEntry,
)
from backend.shopify.port import (
    SHOPIFY_READ_OPERATIONS,
    CommerceState,
    ShopifyReadPort,
)

__all__ = [
    "SHOPIFY_READ_OPERATIONS",
    "CallClassification",
    "CommerceState",
    "DeterministicShopifyFixture",
    "FixtureOutcome",
    "ReadCallLedgerEntry",
    "ShopifyReadPort",
]
