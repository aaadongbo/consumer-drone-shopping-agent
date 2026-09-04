"""Internal S08 locator metadata gate for externally staged corpus records."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.common import ObjectScope

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]

EXPECTED_LANGUAGE = "zh-CN"
EXPECTED_REGION = "China mainland"
MAVIC_3_PRODUCT_ID = "DJI Mavic 3"


class LocatorBindingRejectionReason(StrEnum):
    PRODUCT_SCOPE_MISMATCH = "PRODUCT_SCOPE_MISMATCH"
    VARIANT_SCOPE_MISMATCH = "VARIANT_SCOPE_MISMATCH"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    REGION_MISMATCH = "REGION_MISMATCH"
    SOURCE_REF_MISMATCH = "SOURCE_REF_MISMATCH"
    SOURCE_ID_MISMATCH = "SOURCE_ID_MISMATCH"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    PAGE_MISMATCH = "PAGE_MISMATCH"
    LOCATOR_MISMATCH = "LOCATOR_MISMATCH"
    OVERLAY_SCOPE_MISMATCH = "OVERLAY_SCOPE_MISMATCH"


class OverlayDecision(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ALLOWED = "ALLOWED"
    EXCLUDED = "EXCLUDED"


class LocatorBindingSource(BaseModel):
    """Expected source metadata from the admitted corpus manifest/inventory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref: NonEmptyString
    source_id: NonEmptyString
    version: NonEmptyString
    checksum: NonEmptyString
    pages: int = Field(ge=1)
    product_scope: NonEmptyString
    language: NonEmptyString = EXPECTED_LANGUAGE
    region: NonEmptyString = EXPECTED_REGION


class Mavic3ScopeOverlay(BaseModel):
    """Metadata-only exclusion overlay for standard Mavic 3 locator scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: NonEmptyString
    excluded_pages: tuple[int, ...] = ()


class LocatorBinding(BaseModel):
    """Accepted page locator binding for one Turn Target.

    This is an internal S08 model and intentionally carries no official document text.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref: NonEmptyString
    source_id: NonEmptyString
    version: NonEmptyString
    page_number: int = Field(ge=1)
    locator: NonEmptyString
    product_scope: NonEmptyString
    language: NonEmptyString
    region: NonEmptyString
    checksum: NonEmptyString
    overlay_decision: OverlayDecision

    @model_validator(mode="after")
    def validate_locator_prefix(self) -> LocatorBinding:
        expected_prefix = f"rag://{self.source_id}@{self.version}/"
        if not self.locator.startswith(expected_prefix):
            raise ValueError("locator must start with rag://<source_id>@<version>/")
        return self


class LocatorBindingResult(BaseModel):
    """Fail-closed binding result for one candidate locator record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding: LocatorBinding | None = None
    rejection_reason: LocatorBindingRejectionReason | None = None

    @property
    def accepted(self) -> bool:
        return self.binding is not None and self.rejection_reason is None

    @model_validator(mode="after")
    def validate_result_shape(self) -> LocatorBindingResult:
        if (self.binding is None) == (self.rejection_reason is None):
            raise ValueError("exactly one of binding or rejection_reason is required")
        return self


def bind_locator_record(
    record: dict[str, Any],
    *,
    target_scope: ObjectScope,
    source: LocatorBindingSource,
    overlay: Mavic3ScopeOverlay | None = None,
) -> LocatorBindingResult:
    """Bind one metadata-only page locator to a single Turn Target or reject it."""

    product_scope = _str_or_none(record.get("product_scope"))
    if not _product_scope_matches(product_scope, target_scope.product_id):
        return _reject(LocatorBindingRejectionReason.PRODUCT_SCOPE_MISMATCH)

    record_variant = _str_or_none(record.get("variant_id"))
    if record_variant is not None and record_variant != target_scope.variant_id:
        return _reject(LocatorBindingRejectionReason.VARIANT_SCOPE_MISMATCH)

    language = _str_or_none(record.get("language"))
    if language != source.language:
        return _reject(LocatorBindingRejectionReason.LANGUAGE_MISMATCH)

    region = _str_or_none(record.get("region"))
    if region != source.region:
        return _reject(LocatorBindingRejectionReason.REGION_MISMATCH)

    source_ref = _str_or_none(record.get("source_ref"))
    if source_ref != source.source_ref:
        return _reject(LocatorBindingRejectionReason.SOURCE_REF_MISMATCH)

    source_id = _str_or_none(record.get("source_id"))
    if source_id != source.source_id:
        return _reject(LocatorBindingRejectionReason.SOURCE_ID_MISMATCH)

    version = _str_or_none(record.get("document_version"))
    if version != source.version:
        return _reject(LocatorBindingRejectionReason.VERSION_MISMATCH)

    checksum = _str_or_none(record.get("source_sha256"))
    if checksum != source.checksum:
        return _reject(LocatorBindingRejectionReason.CHECKSUM_MISMATCH)

    page_number = record.get("page_number")
    if not isinstance(page_number, int) or not 1 <= page_number <= source.pages:
        return _reject(LocatorBindingRejectionReason.PAGE_MISMATCH)

    locator = _str_or_none(record.get("locator"))
    expected_locator = f"rag://{source.source_id}@{source.version}/page/{page_number}"
    if locator != expected_locator:
        return _reject(LocatorBindingRejectionReason.LOCATOR_MISMATCH)

    overlay_decision = _overlay_decision(
        target_scope=target_scope,
        source_id=source.source_id,
        page_number=page_number,
        overlay=overlay,
    )
    if overlay_decision is OverlayDecision.EXCLUDED:
        return _reject(LocatorBindingRejectionReason.OVERLAY_SCOPE_MISMATCH)

    return LocatorBindingResult(
        binding=LocatorBinding(
            source_ref=source.source_ref,
            source_id=source.source_id,
            version=source.version,
            page_number=page_number,
            locator=locator,
            product_scope=product_scope,
            language=language,
            region=region,
            checksum=source.checksum,
            overlay_decision=overlay_decision,
        )
    )


def _overlay_decision(
    *,
    target_scope: ObjectScope,
    source_id: str,
    page_number: int,
    overlay: Mavic3ScopeOverlay | None,
) -> OverlayDecision:
    if (
        target_scope.product_id != MAVIC_3_PRODUCT_ID
        or overlay is None
        or overlay.source_id != source_id
    ):
        return OverlayDecision.NOT_APPLICABLE
    if page_number in overlay.excluded_pages:
        return OverlayDecision.EXCLUDED
    return OverlayDecision.ALLOWED


def _product_scope_matches(product_scope: str | None, product_id: str) -> bool:
    if product_scope is None:
        return False
    if product_scope == product_id:
        return True
    return product_scope.startswith(f"{product_id} ")


def _reject(reason: LocatorBindingRejectionReason) -> LocatorBindingResult:
    return LocatorBindingResult(rejection_reason=reason)


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = [
    "LocatorBinding",
    "LocatorBindingRejectionReason",
    "LocatorBindingResult",
    "LocatorBindingSource",
    "Mavic3ScopeOverlay",
    "OverlayDecision",
    "bind_locator_record",
]
