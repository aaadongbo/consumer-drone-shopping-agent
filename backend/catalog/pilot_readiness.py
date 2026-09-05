"""Metadata-only readiness gates for the Slice 10 local pilot."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.rag.chunk_baseline import ChunkBaselineValidationReport
from backend.rag.corpus_readiness import CorpusReadinessReport

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

PILOT_PRODUCT_COUNT = 3


class PilotLaneStatus(StrEnum):
    GO = "GO"
    HOLD = "HOLD"


class PilotReadinessStopReason(StrEnum):
    READY = "READY"
    PILOT_SCOPE_LIMIT = "PILOT_SCOPE_LIMIT"
    PRODUCT_NAME_DUPLICATE = "PRODUCT_NAME_DUPLICATE"
    PRODUCT_SCOPE_MISMATCH = "PRODUCT_SCOPE_MISMATCH"
    STORE_SCOPE_MISMATCH = "STORE_SCOPE_MISMATCH"
    PRODUCT_ID_REQUIRED = "PRODUCT_ID_REQUIRED"
    PRODUCT_ID_DUPLICATE = "PRODUCT_ID_DUPLICATE"
    VARIANT_ID_REQUIRED = "VARIANT_ID_REQUIRED"
    VARIANT_ID_DUPLICATE = "VARIANT_ID_DUPLICATE"
    VARIANT_OWNERSHIP_MISMATCH = "VARIANT_OWNERSHIP_MISMATCH"
    READ_ONLY_CREDENTIAL_REQUIRED = "READ_ONLY_CREDENTIAL_REQUIRED"
    CORPUS_METADATA_REQUIRED = "CORPUS_METADATA_REQUIRED"
    CORPUS_NOT_READY = "CORPUS_NOT_READY"
    CHUNK_BASELINE_REQUIRED = "CHUNK_BASELINE_REQUIRED"
    CHUNK_BASELINE_NOT_READY = "CHUNK_BASELINE_NOT_READY"


class PilotVariantIdentity(BaseModel):
    """Stable metadata for one commerce-bearing Variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString


class PilotProductIdentity(BaseModel):
    """One of the exactly three approved pilot Products."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product_name: NonEmptyString
    store_id: NonEmptyString
    product_id: NonEmptyString | None = None
    variants: tuple[PilotVariantIdentity, ...] = ()


class PilotLaneReport(BaseModel):
    """Safe, serializable result for one independent readiness lane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: PilotLaneStatus
    stop_reason: PilotReadinessStopReason
    accepted_product_count: int = Field(ge=0)
    accepted_variant_count: int = Field(ge=0)
    rejected_reasons: tuple[NonEmptyString, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status is PilotLaneStatus.GO


class PilotDataReadinessReport(BaseModel):
    """Internal T01 report; it contains no credentials or source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    store_id: NonEmptyString
    approved_product_names: tuple[NonEmptyString, ...]
    shopify_lane: PilotLaneReport
    corpus_lane: PilotLaneReport
    accepted_products: tuple[PilotProductIdentity, ...] = ()
    accepted_variant_ids: tuple[NonEmptyString, ...] = ()
    metadata_only: bool = True

    @property
    def ready(self) -> bool:
        return self.shopify_lane.ready and self.corpus_lane.ready

    def to_wire(self) -> dict[str, object]:
        """Return safe metadata without any external payloads or secrets."""

        return self.model_dump(mode="json", exclude_none=True)


def build_pilot_data_readiness_report(
    *,
    store_id: str,
    products: tuple[PilotProductIdentity, ...],
    credential_read_only: bool | None,
    corpus_report: CorpusReadinessReport | None = None,
    chunk_baseline_report: ChunkBaselineValidationReport | None = None,
    approved_product_names: tuple[str, ...],
) -> PilotDataReadinessReport:
    """Assess pilot metadata without network, credential, or file writes.

    ``credential_read_only`` is a caller-provided metadata verdict.  This function
    never loads or logs credentials and therefore cannot turn an unknown scope into
    an affirmative readiness result.
    """

    store = _non_empty(store_id)
    names = tuple(_non_empty(name) for name in approved_product_names)
    shopify = _shopify_lane(
        store_id=store,
        products=products,
        credential_read_only=credential_read_only,
        approved_product_names=names,
    )
    corpus = _corpus_lane(corpus_report, chunk_baseline_report)
    accepted_products = tuple(
        product
        for product in products
        if product.store_id == store and product.product_id
    )
    variant_ids = tuple(
        variant.variant_id
        for product in accepted_products
        for variant in product.variants
        if variant.store_id == store and variant.product_id == product.product_id
    )
    return PilotDataReadinessReport(
        store_id=store,
        approved_product_names=names,
        shopify_lane=shopify,
        corpus_lane=corpus,
        accepted_products=accepted_products,
        accepted_variant_ids=variant_ids,
    )


def _shopify_lane(
    *,
    store_id: str,
    products: tuple[PilotProductIdentity, ...],
    credential_read_only: bool | None,
    approved_product_names: tuple[str, ...],
) -> PilotLaneReport:
    reasons: list[str] = []
    if (
        len(approved_product_names) != PILOT_PRODUCT_COUNT
        or len(products) != PILOT_PRODUCT_COUNT
    ):
        reasons.append(PilotReadinessStopReason.PILOT_SCOPE_LIMIT.value)
    if len({product.product_name for product in products}) != len(products):
        reasons.append("PRODUCT_NAME_DUPLICATE")
    if set(product.product_name for product in products) != set(approved_product_names):
        reasons.append("PRODUCT_SCOPE_MISMATCH")
    product_ids = [product.product_id for product in products if product.product_id]
    if len(product_ids) != len(products):
        reasons.append(PilotReadinessStopReason.PRODUCT_ID_REQUIRED.value)
    if len(product_ids) != len(set(product_ids)):
        reasons.append(PilotReadinessStopReason.PRODUCT_ID_DUPLICATE.value)
    variant_ids = [
        variant.variant_id for product in products for variant in product.variants
    ]
    if not variant_ids:
        reasons.append(PilotReadinessStopReason.VARIANT_ID_REQUIRED.value)
    if len(variant_ids) != len(set(variant_ids)):
        reasons.append(PilotReadinessStopReason.VARIANT_ID_DUPLICATE.value)
    for product in products:
        if product.store_id != store_id:
            reasons.append(PilotReadinessStopReason.STORE_SCOPE_MISMATCH.value)
        for variant in product.variants:
            if variant.store_id != store_id or variant.product_id != product.product_id:
                reasons.append(
                    PilotReadinessStopReason.VARIANT_OWNERSHIP_MISMATCH.value
                )
    if credential_read_only is not True:
        reasons.append(PilotReadinessStopReason.READ_ONLY_CREDENTIAL_REQUIRED.value)
    unique_reasons = tuple(dict.fromkeys(reasons))
    ready = not unique_reasons
    return PilotLaneReport(
        status=PilotLaneStatus.GO if ready else PilotLaneStatus.HOLD,
        stop_reason=PilotReadinessStopReason.READY
        if ready
        else PilotReadinessStopReason(unique_reasons[0]),
        accepted_product_count=len(products) if ready else 0,
        accepted_variant_count=len(variant_ids) if ready else 0,
        rejected_reasons=unique_reasons,
    )


def _corpus_lane(
    corpus_report: CorpusReadinessReport | None,
    chunk_baseline_report: ChunkBaselineValidationReport | None,
) -> PilotLaneReport:
    if corpus_report is None:
        return _hold(PilotReadinessStopReason.CORPUS_METADATA_REQUIRED)
    if not corpus_report.metadata_accepted:
        return _hold(PilotReadinessStopReason.CORPUS_NOT_READY)
    if chunk_baseline_report is None:
        return _hold(PilotReadinessStopReason.CHUNK_BASELINE_REQUIRED)
    if not chunk_baseline_report.accepted:
        return _hold(PilotReadinessStopReason.CHUNK_BASELINE_NOT_READY)
    return PilotLaneReport(
        status=PilotLaneStatus.GO,
        stop_reason=PilotReadinessStopReason.READY,
        accepted_product_count=3,
        accepted_variant_count=0,
    )


def _hold(reason: PilotReadinessStopReason) -> PilotLaneReport:
    return PilotLaneReport(
        status=PilotLaneStatus.HOLD,
        stop_reason=reason,
        accepted_product_count=0,
        accepted_variant_count=0,
        rejected_reasons=(reason.value,),
    )


def _non_empty(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("metadata values must be non-empty")
    return stripped


__all__ = [
    "PILOT_PRODUCT_COUNT",
    "PilotDataReadinessReport",
    "PilotLaneReport",
    "PilotLaneStatus",
    "PilotProductIdentity",
    "PilotReadinessStopReason",
    "PilotVariantIdentity",
    "build_pilot_data_readiness_report",
]
