"""T09 exact Product/Variant storefront destination checks."""

import pytest

from backend.common import ObjectScope
from storefront.product_links import (
    LinkConfigurationError,
    ProductVariantLink,
    StorefrontLinkRegistry,
)

pytestmark = pytest.mark.unit

STORE = "shopify-store:bys-user-store-578412-7a11gk0u"
SCOPE = ObjectScope(store_id=STORE, product_id="p1", variant_id="v1")


def test_registry_resolves_only_exact_identity() -> None:
    registry = StorefrontLinkRegistry(
        (ProductVariantLink(STORE, "p1", "v1", "https://shop.example/products/mini"),),
        support_url="https://shop.example/pages/support",
    )
    assert registry.resolve(SCOPE) == "https://shop.example/products/mini"
    assert registry.support_url.endswith("/pages/support")
    with pytest.raises(LinkConfigurationError):
        registry.resolve(SCOPE.model_copy(update={"variant_id": "v2"}))


@pytest.mark.parametrize(
    "url",
    [
        "http://shop.example/products/p1",
        "https://shop.example/",
        "*",
        "https://shop.example/products/p1#x",
    ],
)
def test_registry_rejects_unapproved_or_ambiguous_destinations(url: str) -> None:
    with pytest.raises(LinkConfigurationError):
        StorefrontLinkRegistry((ProductVariantLink(STORE, "p1", "v1", url),))
