"""Exact, checksum-bound identity bindings for external corpus metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.common import ObjectScope

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
type Sha256String = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class CorpusScopeBindingRejectionReason(StrEnum):
    """Fail-closed reasons for rejecting a corpus identity lookup."""

    SCOPE_NOT_BOUND = "SCOPE_NOT_BOUND"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    AMBIGUOUS_BINDING = "AMBIGUOUS_BINDING"


class CorpusScopeBindingError(ValueError):
    """A corpus key did not resolve to one approved canonical scope."""

    def __init__(self, reason: CorpusScopeBindingRejectionReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class CorpusScopeBinding(BaseModel):
    """One approved exact mapping from corpus identity to canonical scope.

    Corpus keys are intentionally opaque.  They are never normalized into names,
    slugs, aliases, or fuzzy matches at this boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    corpus_store_id: NonEmptyString
    corpus_product_key: NonEmptyString
    corpus_variant_key: NonEmptyString | None = None
    manifest_sha256: Sha256String
    canonical_scope: ObjectScope

    @property
    def lookup_key(self) -> tuple[str, str, str | None, str]:
        """Return the complete checksum-bound lookup identity."""
        return (
            self.corpus_store_id,
            self.corpus_product_key,
            self.corpus_variant_key,
            self.manifest_sha256,
        )


class CorpusScopeBindingRegistry(BaseModel):
    """Immutable allowlist of approved corpus-to-Shopify identity mappings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bindings: tuple[CorpusScopeBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_lookup_keys(self) -> CorpusScopeBindingRegistry:
        keys = [binding.lookup_key for binding in self.bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("corpus scope binding lookup keys must be unique")
        return self


class CorpusScopeBindingResult(BaseModel):
    """Typed result for an exact corpus identity lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding: CorpusScopeBinding | None = None
    rejection_reason: CorpusScopeBindingRejectionReason | None = None

    @property
    def accepted(self) -> bool:
        return self.binding is not None and self.rejection_reason is None

    @property
    def canonical_scope(self) -> ObjectScope | None:
        return self.binding.canonical_scope if self.binding is not None else None

    @model_validator(mode="after")
    def validate_result_shape(self) -> CorpusScopeBindingResult:
        if (self.binding is None) == (self.rejection_reason is None):
            raise ValueError("exactly one of binding or rejection_reason is required")
        return self


def bind_corpus_scope(
    registry: CorpusScopeBindingRegistry,
    *,
    corpus_store_id: str,
    corpus_product_key: str,
    corpus_variant_key: str | None,
    manifest_sha256: str,
    expected_manifest_sha256: str | None = None,
) -> CorpusScopeBindingResult:
    """Resolve one corpus identity using exact key and checksum equality."""

    if (
        expected_manifest_sha256 is not None
        and manifest_sha256 != expected_manifest_sha256
    ):
        return _reject(CorpusScopeBindingRejectionReason.CHECKSUM_MISMATCH)

    identity_matches = tuple(
        binding
        for binding in registry.bindings
        if (
            binding.corpus_store_id == corpus_store_id
            and binding.corpus_product_key == corpus_product_key
            and binding.corpus_variant_key == corpus_variant_key
        )
    )
    if not identity_matches:
        return _reject(CorpusScopeBindingRejectionReason.SCOPE_NOT_BOUND)

    checksum_matches = tuple(
        binding
        for binding in identity_matches
        if binding.manifest_sha256 == manifest_sha256
    )
    if not checksum_matches:
        return _reject(CorpusScopeBindingRejectionReason.CHECKSUM_MISMATCH)
    if len(checksum_matches) != 1:
        return _reject(CorpusScopeBindingRejectionReason.AMBIGUOUS_BINDING)
    return CorpusScopeBindingResult(binding=checksum_matches[0])


def resolve_corpus_scope(
    registry: CorpusScopeBindingRegistry,
    *,
    corpus_store_id: str,
    corpus_product_key: str,
    corpus_variant_key: str | None,
    manifest_sha256: str,
    expected_manifest_sha256: str | None = None,
) -> ObjectScope:
    """Return the canonical scope or raise a typed fail-closed error."""

    result = bind_corpus_scope(
        registry,
        corpus_store_id=corpus_store_id,
        corpus_product_key=corpus_product_key,
        corpus_variant_key=corpus_variant_key,
        manifest_sha256=manifest_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    if result.binding is None or result.rejection_reason is not None:
        raise CorpusScopeBindingError(
            result.rejection_reason or CorpusScopeBindingRejectionReason.SCOPE_NOT_BOUND
        )
    return result.binding.canonical_scope


def _reject(reason: CorpusScopeBindingRejectionReason) -> CorpusScopeBindingResult:
    return CorpusScopeBindingResult(rejection_reason=reason)


__all__ = [
    "CorpusScopeBinding",
    "CorpusScopeBindingError",
    "CorpusScopeBindingRegistry",
    "CorpusScopeBindingRejectionReason",
    "CorpusScopeBindingResult",
    "bind_corpus_scope",
    "resolve_corpus_scope",
]
