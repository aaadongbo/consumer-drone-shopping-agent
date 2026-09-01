"""Deterministic, store-scoped resolution of already identified object references."""

from collections.abc import Iterable
from enum import StrEnum

from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import ObjectScope
from backend.common.contracts import NonEmptyString, WireModel


class ExplicitReference(WireModel):
    """An already extracted explicit product and/or variant surface form."""

    product_name: NonEmptyString | None = None
    variant_name: NonEmptyString | None = None


class CatalogAlias(WireModel):
    """A deliberately configured alias for one store-owned catalog object."""

    alias: NonEmptyString
    scope: ObjectScope


class ReferenceResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class ReferenceClarificationReason(StrEnum):
    EMPTY_REFERENCE = "EMPTY_REFERENCE"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    PRODUCT_AMBIGUOUS = "PRODUCT_AMBIGUOUS"
    VARIANT_NOT_FOUND = "VARIANT_NOT_FOUND"
    VARIANT_AMBIGUOUS = "VARIANT_AMBIGUOUS"
    VARIANT_NOT_OWNED_BY_PRODUCT = "VARIANT_NOT_OWNED_BY_PRODUCT"


class ExplicitReferenceResolution(WireModel):
    """A resolved identity or a fail-closed clarification result."""

    status: ReferenceResolutionStatus
    scope: ObjectScope | None = None
    clarification_reason: ReferenceClarificationReason | None = None
    candidates: tuple[ObjectScope, ...] = ()

    def model_post_init(self, __context: object) -> None:
        if self.status is ReferenceResolutionStatus.RESOLVED:
            if (
                self.scope is None
                or self.clarification_reason is not None
                or self.candidates
            ):
                raise ValueError("resolved reference requires exactly one scope")
        elif self.scope is not None or self.clarification_reason is None:
            raise ValueError("clarification requires a reason and no resolved scope")


class CatalogReferenceResolver:
    """Resolve exact names and controlled aliases without catalog or commerce reads."""

    def __init__(
        self,
        *,
        snapshot: CatalogFixtureSnapshot,
        aliases: Iterable[CatalogAlias] = (),
    ) -> None:
        self._store_id = snapshot.store_id
        self._products = tuple(snapshot.products)
        self._variants = tuple(snapshot.variants)
        self._aliases = tuple(aliases)
        self._validate_aliases()

    def resolve(self, reference: ExplicitReference) -> ExplicitReferenceResolution:
        """Return one owned identity, otherwise a stable clarification result."""
        if reference.product_name is None and reference.variant_name is None:
            return _clarification(ReferenceClarificationReason.EMPTY_REFERENCE)

        products = (
            self._product_candidates(reference.product_name)
            if reference.product_name is not None
            else ()
        )
        variants = (
            self._variant_candidates(reference.variant_name)
            if reference.variant_name is not None
            else ()
        )

        if reference.product_name is not None:
            product_failure = _candidate_failure(
                products,
                ReferenceClarificationReason.PRODUCT_NOT_FOUND,
                ReferenceClarificationReason.PRODUCT_AMBIGUOUS,
            )
            if product_failure is not None:
                return product_failure

        if reference.variant_name is not None:
            variant_failure = _candidate_failure(
                variants,
                ReferenceClarificationReason.VARIANT_NOT_FOUND,
                ReferenceClarificationReason.VARIANT_AMBIGUOUS,
            )
            if variant_failure is not None:
                return variant_failure

        if products and variants:
            product = products[0]
            variant = variants[0]
            if variant.product_id != product.product_id:
                return _clarification(
                    ReferenceClarificationReason.VARIANT_NOT_OWNED_BY_PRODUCT,
                    candidates=(product, variant),
                )
            return _resolved(variant)
        return _resolved(products[0] if products else variants[0])

    def _product_candidates(self, name: str) -> tuple[ObjectScope, ...]:
        normalized = _normalize(name)
        candidates = [
            ObjectScope(store_id=self._store_id, product_id=product.product_id)
            for product in self._products
            if normalized
            in {_normalize(product.product_id), _normalize(product.display_title)}
        ]
        candidates.extend(
            alias.scope
            for alias in self._aliases
            if alias.scope.variant_id is None and _normalize(alias.alias) == normalized
        )
        return _unique(candidates)

    def _variant_candidates(self, name: str) -> tuple[ObjectScope, ...]:
        normalized = _normalize(name)
        candidates = [
            ObjectScope(
                store_id=self._store_id,
                product_id=variant.product_id,
                variant_id=variant.variant_id,
            )
            for variant in self._variants
            if normalized
            in {_normalize(variant.variant_id), _normalize(variant.display_label)}
        ]
        candidates.extend(
            alias.scope
            for alias in self._aliases
            if alias.scope.variant_id is not None
            and _normalize(alias.alias) == normalized
        )
        return _unique(candidates)

    def _validate_aliases(self) -> None:
        product_ids = {product.product_id for product in self._products}
        variant_scopes = {
            (variant.product_id, variant.variant_id) for variant in self._variants
        }
        for alias in self._aliases:
            if alias.scope.store_id != self._store_id:
                raise ValueError("Catalog alias crossed the resolver store boundary")
            if alias.scope.variant_id is None:
                if alias.scope.product_id not in product_ids:
                    raise ValueError("Catalog alias references an unknown product")
            elif (alias.scope.product_id, alias.scope.variant_id) not in variant_scopes:
                raise ValueError(
                    "Catalog alias references an unknown variant ownership"
                )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _unique(candidates: Iterable[ObjectScope]) -> tuple[ObjectScope, ...]:
    return tuple(dict.fromkeys(candidates))


def _candidate_failure(
    candidates: tuple[ObjectScope, ...],
    not_found: ReferenceClarificationReason,
    ambiguous: ReferenceClarificationReason,
) -> ExplicitReferenceResolution | None:
    if not candidates:
        return _clarification(not_found)
    if len(candidates) > 1:
        return _clarification(ambiguous, candidates=candidates)
    return None


def _resolved(scope: ObjectScope) -> ExplicitReferenceResolution:
    return ExplicitReferenceResolution(
        status=ReferenceResolutionStatus.RESOLVED,
        scope=scope,
    )


def _clarification(
    reason: ReferenceClarificationReason,
    *,
    candidates: tuple[ObjectScope, ...] = (),
) -> ExplicitReferenceResolution:
    return ExplicitReferenceResolution(
        status=ReferenceResolutionStatus.NEEDS_CLARIFICATION,
        clarification_reason=reason,
        candidates=candidates,
    )
