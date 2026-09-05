"""Protocol-independent, read-only Shopify boundary for Slice 1."""

from backend.shopify.adapter import RealShopifyReadAdapter, ShopifyAdapterStopReason
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
from backend.shopify.transport import (
    MacOSKeychainAccessTokenProvider,
    ShopifyCredentialError,
    ShopifyReadTransport,
    ShopifyTokenProvider,
    ShopifyTransportFailure,
    ShopifyTransportResult,
    UrllibShopifyReadTransport,
)

__all__ = [
    "SHOPIFY_READ_OPERATIONS",
    "CallClassification",
    "CommerceState",
    "DeterministicShopifyFixture",
    "FixtureOutcome",
    "ReadCallLedgerEntry",
    "RealShopifyReadAdapter",
    "ShopifyAdapterStopReason",
    "MacOSKeychainAccessTokenProvider",
    "ShopifyCredentialError",
    "ShopifyReadTransport",
    "ShopifyTransportFailure",
    "ShopifyTransportResult",
    "ShopifyTokenProvider",
    "ShopifyReadPort",
    "UrllibShopifyReadTransport",
]
