"""S08-T02 contract coverage for locator-to-SourceLocator compatibility."""

import pytest

from backend.common import ObjectScope
from backend.rag import (
    LocatorBindingSource,
    SourceLocator,
    bind_locator_record,
)

pytestmark = pytest.mark.contract


def test_bound_locator_reuses_existing_source_locator_semantics() -> None:
    source = LocatorBindingSource(
        source_ref="official-manual-mini-3-zh-cn-v1.2-20260423",
        source_id="dji-mini-3-manual-zh-cn-v1.2",
        version="v1.2",
        checksum="64f06971c787592f2731dca47de9cb4ead811371427cb09b60ff074c0a4e3fea",
        pages=66,
        product_scope="DJI Mini 3 only",
    )

    result = bind_locator_record(
        {
            "record_type": "ordered_page_locator",
            "source_ref": source.source_ref,
            "source_id": source.source_id,
            "source_sha256": source.checksum,
            "product_scope": source.product_scope,
            "language": "zh-CN",
            "region": "China mainland",
            "document_version": source.version,
            "page_number": 12,
            "locator": "rag://dji-mini-3-manual-zh-cn-v1.2@v1.2/page/12",
        },
        target_scope=ObjectScope(
            store_id="store-s08-metadata",
            product_id="DJI Mini 3",
        ),
        source=source,
    )

    assert result.binding is not None
    assert (
        SourceLocator(
            source_id=result.binding.source_id,
            version=result.binding.version,
            locator=result.binding.locator,
        ).locator
        == result.binding.locator
    )
