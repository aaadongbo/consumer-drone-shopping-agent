"""S08-T02 unit coverage for metadata-only locator binding."""

import pytest

from backend.common import ObjectScope
from backend.rag import (
    LocatorBindingRejectionReason,
    LocatorBindingSource,
    Mavic3ScopeOverlay,
    OverlayDecision,
    bind_locator_record,
)

pytestmark = pytest.mark.unit


MINI_SHA256 = "64f06971c787592f2731dca47de9cb4ead811371427cb09b60ff074c0a4e3fea"
AIR_SHA256 = "f6134ef3bd41cefd226bc56b40b376d86b348c60489c4006472364d5d2fbfd23"
MAVIC_SHA256 = "f5a6d4148726450cdb0b72de1598d31a2ea478a044182d4b8da4941d935070fa"


@pytest.mark.parametrize(
    ("product_id", "source", "page_number", "overlay_decision"),
    [
        (
            "DJI Mini 3",
            LocatorBindingSource(
                source_ref="official-manual-mini-3-zh-cn-v1.2-20260423",
                source_id="dji-mini-3-manual-zh-cn-v1.2",
                version="v1.2",
                checksum=MINI_SHA256,
                pages=66,
                product_scope="DJI Mini 3 only",
            ),
            12,
            OverlayDecision.NOT_APPLICABLE,
        ),
        (
            "DJI Air 3",
            LocatorBindingSource(
                source_ref="official-manual-air-3-zh-cn-v1.6-20240627",
                source_id="dji-air-3-manual-zh-cn-v1.6",
                version="v1.6",
                checksum=AIR_SHA256,
                pages=109,
                product_scope="DJI Air 3 only",
            ),
            21,
            OverlayDecision.NOT_APPLICABLE,
        ),
        (
            "DJI Mavic 3",
            LocatorBindingSource(
                source_ref="official-manual-mavic-3-zh-cn-v2.3-20240606",
                source_id="dji-mavic-3-manual-zh-cn-v2.3",
                version="v2.3",
                checksum=MAVIC_SHA256,
                pages=86,
                product_scope="DJI Mavic 3 only; Cine excluded by overlay",
            ),
            5,
            OverlayDecision.ALLOWED,
        ),
    ],
)
def test_locator_passes_only_for_its_own_target_scope(
    product_id: str,
    source: LocatorBindingSource,
    page_number: int,
    overlay_decision: OverlayDecision,
) -> None:
    result = bind_locator_record(
        _record(source, page_number=page_number),
        target_scope=_scope(product_id),
        source=source,
        overlay=_mavic_overlay(),
    )

    assert result.accepted is True
    assert result.binding is not None
    assert result.binding.source_ref == source.source_ref
    assert result.binding.source_id == source.source_id
    assert result.binding.version == source.version
    assert result.binding.page_number == page_number
    assert result.binding.product_scope == source.product_scope
    assert result.binding.language == "zh-CN"
    assert result.binding.region == "China mainland"
    assert result.binding.checksum == source.checksum
    assert result.binding.overlay_decision is overlay_decision


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("product_scope", "DJI Air 3 only", "PRODUCT_SCOPE_MISMATCH"),
        ("variant_id", "cine-premium", "VARIANT_SCOPE_MISMATCH"),
        ("language", "en-US", "LANGUAGE_MISMATCH"),
        ("region", "United States", "REGION_MISMATCH"),
        ("source_ref", "official-manual-other", "SOURCE_REF_MISMATCH"),
        ("source_id", "dji-mini-3-manual-other", "SOURCE_ID_MISMATCH"),
        ("document_version", "v9.9", "VERSION_MISMATCH"),
        ("source_sha256", "0" * 64, "CHECKSUM_MISMATCH"),
        ("page_number", 67, "PAGE_MISMATCH"),
        ("locator", "rag://dji-mini-3-manual-zh-cn-v1.2/page/99", "LOCATOR_MISMATCH"),
    ],
)
def test_locator_mismatch_reasons_are_precise(
    field: str,
    value: object,
    reason: str,
) -> None:
    source = _mini_source()
    record = _record(source, page_number=12)
    record[field] = value

    result = bind_locator_record(
        record,
        target_scope=_scope("DJI Mini 3", variant_id="standard-pack"),
        source=source,
    )

    assert result.accepted is False
    assert result.binding is None
    assert result.rejection_reason is LocatorBindingRejectionReason(reason)


def test_cross_product_locator_injection_is_rejected_before_binding() -> None:
    result = bind_locator_record(
        _record(_mini_source(), page_number=12),
        target_scope=_scope("DJI Air 3"),
        source=_mini_source(),
    )

    assert result.accepted is False
    assert (
        result.rejection_reason is LocatorBindingRejectionReason.PRODUCT_SCOPE_MISMATCH
    )


def test_mavic_3_cine_overlay_page_is_rejected() -> None:
    source = _mavic_source()

    result = bind_locator_record(
        _record(source, page_number=3),
        target_scope=_scope("DJI Mavic 3"),
        source=source,
        overlay=_mavic_overlay(),
    )

    assert result.accepted is False
    assert (
        result.rejection_reason is LocatorBindingRejectionReason.OVERLAY_SCOPE_MISMATCH
    )


def _scope(product_id: str, variant_id: str | None = None) -> ObjectScope:
    return ObjectScope(
        store_id="store-s08-metadata",
        product_id=product_id,
        variant_id=variant_id,
    )


def _mini_source() -> LocatorBindingSource:
    return LocatorBindingSource(
        source_ref="official-manual-mini-3-zh-cn-v1.2-20260423",
        source_id="dji-mini-3-manual-zh-cn-v1.2",
        version="v1.2",
        checksum=MINI_SHA256,
        pages=66,
        product_scope="DJI Mini 3 only",
    )


def _mavic_source() -> LocatorBindingSource:
    return LocatorBindingSource(
        source_ref="official-manual-mavic-3-zh-cn-v2.3-20240606",
        source_id="dji-mavic-3-manual-zh-cn-v2.3",
        version="v2.3",
        checksum=MAVIC_SHA256,
        pages=86,
        product_scope="DJI Mavic 3 only; Cine excluded by overlay",
    )


def _mavic_overlay() -> Mavic3ScopeOverlay:
    return Mavic3ScopeOverlay(
        source_id="dji-mavic-3-manual-zh-cn-v2.3",
        excluded_pages=(3,),
    )


def _record(
    source: LocatorBindingSource,
    *,
    page_number: int,
    variant_id: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "record_type": "ordered_page_locator",
        "source_ref": source.source_ref,
        "source_id": source.source_id,
        "source_sha256": source.checksum,
        "product_scope": source.product_scope,
        "language": source.language,
        "region": source.region,
        "document_version": source.version,
        "page_number": page_number,
        "locator": f"rag://{source.source_id}@{source.version}/page/{page_number}",
        "ordinal": page_number,
        "text_sha256": "1" * 64,
        "extraction_method": "metadata-only fixture",
        "warnings": [],
    }
    if variant_id is not None:
        record["variant_id"] = variant_id
    return record
