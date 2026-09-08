"""Fail-closed, identity-bound storefront destinations for the beta Widget."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse

from backend.common import ObjectScope


class LinkConfigurationError(ValueError):
    """Raised when a storefront destination is not explicitly approved."""


@dataclass(frozen=True, slots=True)
class ProductVariantLink:
    store_id: str
    product_id: str
    variant_id: str
    url: str

    def __post_init__(self) -> None:
        _validate_url(self.url, product=True)

    @property
    def scope(self) -> ObjectScope:
        return ObjectScope(
            store_id=self.store_id,
            product_id=self.product_id,
            variant_id=self.variant_id,
        )


class StorefrontLinkRegistry:
    """Resolve only exact mappings supplied by an approved store manifest."""

    def __init__(
        self,
        links: tuple[ProductVariantLink, ...],
        *,
        support_url: str | None = None,
        allowed_origin: str | None = None,
    ) -> None:
        self._allowed_origin = (
            _validate_origin(allowed_origin) if allowed_origin else None
        )
        keys = [(item.store_id, item.product_id, item.variant_id) for item in links]
        if len(keys) != len(set(keys)):
            raise LinkConfigurationError("duplicate Product/Variant storefront link")
        self._links = {key: item.url for key, item in zip(keys, links, strict=True)}
        if self._allowed_origin is not None and any(
            _origin(item.url) != self._allowed_origin for item in links
        ):
            raise LinkConfigurationError("Product link origin is not approved")
        self._support_url = (
            _validate_url(support_url, product=False)
            if support_url is not None
            else None
        )
        if self._allowed_origin is not None and self._support_url is not None:
            if _origin(self._support_url) != self._allowed_origin:
                raise LinkConfigurationError("support URL origin is not approved")

    def resolve(self, scope: ObjectScope) -> str:
        if scope.variant_id is None:
            raise LinkConfigurationError("storefront links require an exact Variant")
        try:
            return self._links[(scope.store_id, scope.product_id, scope.variant_id)]
        except KeyError as error:
            raise LinkConfigurationError(
                "no approved storefront link for scope"
            ) from error

    @property
    def support_url(self) -> str:
        if self._support_url is None:
            raise LinkConfigurationError("support destination is not configured")
        return self._support_url

    @classmethod
    def from_json(
        cls,
        raw: str,
        *,
        support_url: str | None = None,
        allowed_origin: str | None = None,
    ) -> StorefrontLinkRegistry:
        """Load an explicit JSON mapping; display names and handles are ignored."""
        try:
            values = json.loads(raw)
        except json.JSONDecodeError as error:
            raise LinkConfigurationError("invalid storefront link manifest") from error
        if not isinstance(values, list):
            raise LinkConfigurationError("storefront link manifest must be a list")
        links: list[ProductVariantLink] = []
        for value in values:
            if not isinstance(value, dict):
                raise LinkConfigurationError("storefront link entry must be an object")
            try:
                links.append(ProductVariantLink(**value))
            except TypeError as error:
                raise LinkConfigurationError(
                    "storefront link entry is incomplete"
                ) from error
        return cls(tuple(links), support_url=support_url, allowed_origin=allowed_origin)


def _validate_url(url: str | None, *, product: bool) -> str:
    if not isinstance(url, str):
        raise LinkConfigurationError("storefront destination must be an HTTPS URL")
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise LinkConfigurationError("storefront destination must be an HTTPS URL")
    if parsed.fragment:
        raise LinkConfigurationError(
            "storefront destination must not contain a fragment"
        )
    if product and not parsed.path.startswith("/products/"):
        raise LinkConfigurationError("Product links must use the Shopify products path")
    return url


def _validate_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise LinkConfigurationError("allowed storefront origin must be exact HTTPS")
    return origin


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


__all__ = ["LinkConfigurationError", "ProductVariantLink", "StorefrontLinkRegistry"]
