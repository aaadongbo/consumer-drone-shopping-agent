"""RAG-R01 exact corpus identity binding coverage."""

import pytest
from pydantic import ValidationError

from backend.common import ObjectScope
from backend.rag import (
    CorpusScopeBinding,
    CorpusScopeBindingRegistry,
    CorpusScopeBindingRejectionReason,
    bind_corpus_scope,
    resolve_corpus_scope,
)

pytestmark = pytest.mark.unit

MANIFEST_SHA256 = "a" * 64


def test_exact_checksum_bound_key_resolves_to_canonical_scope() -> None:
    registry = _registry()

    result = bind_corpus_scope(
        registry,
        corpus_store_id="corpus-store-1",
        corpus_product_key="catalog-product-123",
        corpus_variant_key="catalog-variant-a",
        manifest_sha256=MANIFEST_SHA256,
    )

    assert result.accepted is True
    assert result.canonical_scope == ObjectScope(
        store_id="shopify-store-1",
        product_id="shopify-product-123",
        variant_id="shopify-variant-a",
    )
    assert (
        resolve_corpus_scope(
            registry,
            corpus_store_id="corpus-store-1",
            corpus_product_key="catalog-product-123",
            corpus_variant_key="catalog-variant-a",
            manifest_sha256=MANIFEST_SHA256,
        )
        == result.canonical_scope
    )


def test_manifest_checksum_mismatch_rejects_before_scope_resolution() -> None:
    result = bind_corpus_scope(
        _registry(),
        corpus_store_id="corpus-store-1",
        corpus_product_key="catalog-product-123",
        corpus_variant_key="catalog-variant-a",
        manifest_sha256="b" * 64,
    )

    assert result.accepted is False
    assert (
        result.rejection_reason is CorpusScopeBindingRejectionReason.CHECKSUM_MISMATCH
    )


def test_expected_manifest_checksum_is_an_additional_binding_gate() -> None:
    result = bind_corpus_scope(
        _registry(),
        corpus_store_id="corpus-store-1",
        corpus_product_key="catalog-product-123",
        corpus_variant_key=None,
        manifest_sha256=MANIFEST_SHA256,
        expected_manifest_sha256="b" * 64,
    )

    assert (
        result.rejection_reason is CorpusScopeBindingRejectionReason.CHECKSUM_MISMATCH
    )


def test_unknown_name_or_slug_has_no_fallback() -> None:
    result = bind_corpus_scope(
        _registry(),
        corpus_store_id="corpus-store-1",
        corpus_product_key="DJI Mini 3",
        corpus_variant_key=None,
        manifest_sha256=MANIFEST_SHA256,
    )

    assert result.rejection_reason is CorpusScopeBindingRejectionReason.SCOPE_NOT_BOUND


def test_duplicate_exact_binding_is_rejected() -> None:
    binding = _registry().bindings[0]

    with pytest.raises(ValidationError, match="lookup keys must be unique"):
        CorpusScopeBindingRegistry(bindings=(binding, binding))


def _registry() -> CorpusScopeBindingRegistry:
    return CorpusScopeBindingRegistry(
        bindings=(
            CorpusScopeBinding(
                corpus_store_id="corpus-store-1",
                corpus_product_key="catalog-product-123",
                manifest_sha256=MANIFEST_SHA256,
                canonical_scope=ObjectScope(
                    store_id="shopify-store-1",
                    product_id="shopify-product-123",
                ),
            ),
            CorpusScopeBinding(
                corpus_store_id="corpus-store-1",
                corpus_product_key="catalog-product-123",
                corpus_variant_key="catalog-variant-a",
                manifest_sha256=MANIFEST_SHA256,
                canonical_scope=ObjectScope(
                    store_id="shopify-store-1",
                    product_id="shopify-product-123",
                    variant_id="shopify-variant-a",
                ),
            ),
        )
    )
