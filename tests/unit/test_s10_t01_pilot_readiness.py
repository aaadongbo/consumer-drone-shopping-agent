"""S10-T01 metadata-only pilot readiness tests."""

import pytest

from backend.catalog import (
    PilotLaneStatus,
    PilotProductIdentity,
    PilotReadinessStopReason,
    PilotVariantIdentity,
    build_pilot_data_readiness_report,
)

pytestmark = pytest.mark.unit

STORE = "store-dji-cn"
PRODUCT_NAMES = ("DJI Mini 3", "DJI Air 3", "DJI Mavic 3")


def _products() -> tuple[PilotProductIdentity, ...]:
    return tuple(
        PilotProductIdentity(
            product_name=name,
            store_id=STORE,
            product_id=f"gid://shopify/Product/{index}",
            variants=(
                PilotVariantIdentity(
                    store_id=STORE,
                    product_id=f"gid://shopify/Product/{index}",
                    variant_id=f"gid://shopify/ProductVariant/{index}",
                ),
            ),
        )
        for index, name in enumerate(PRODUCT_NAMES, start=1)
    )


def test_missing_external_prerequisites_hold_each_lane_without_io() -> None:
    report = build_pilot_data_readiness_report(
        store_id=STORE,
        products=_products(),
        credential_read_only=None,
        approved_product_names=PRODUCT_NAMES,
    )

    assert report.shopify_lane.status is PilotLaneStatus.HOLD
    assert (
        report.shopify_lane.stop_reason
        is PilotReadinessStopReason.READ_ONLY_CREDENTIAL_REQUIRED
    )
    assert (
        report.corpus_lane.stop_reason
        is PilotReadinessStopReason.CORPUS_METADATA_REQUIRED
    )
    assert report.ready is False
    assert report.to_wire()["metadata_only"] is True


def test_complete_identity_is_accepted_but_corpus_can_remain_hold() -> None:
    report = build_pilot_data_readiness_report(
        store_id=STORE,
        products=_products(),
        credential_read_only=True,
        approved_product_names=PRODUCT_NAMES,
    )

    assert report.shopify_lane.status is PilotLaneStatus.GO
    assert report.shopify_lane.accepted_product_count == 3
    assert report.shopify_lane.accepted_variant_count == 3
    assert report.corpus_lane.status is PilotLaneStatus.HOLD


def test_duplicate_and_foreign_variant_fail_closed() -> None:
    products = list(_products())
    products[1] = products[1].model_copy(
        update={
            "variants": (
                PilotVariantIdentity(
                    store_id=STORE,
                    product_id=products[0].product_id,
                    variant_id=products[0].variants[0].variant_id,
                ),
            )
        }
    )
    report = build_pilot_data_readiness_report(
        store_id=STORE,
        products=tuple(products),
        credential_read_only=True,
        approved_product_names=PRODUCT_NAMES,
    )

    assert report.shopify_lane.status is PilotLaneStatus.HOLD
    assert (
        PilotReadinessStopReason.VARIANT_ID_DUPLICATE.value
        in report.shopify_lane.rejected_reasons
    )
    assert (
        PilotReadinessStopReason.VARIANT_OWNERSHIP_MISMATCH.value
        in report.shopify_lane.rejected_reasons
    )


@pytest.mark.parametrize(
    ("product_update", "expected"),
    [
        ({"product_id": None}, PilotReadinessStopReason.PRODUCT_ID_REQUIRED),
        ({"store_id": "store-other"}, PilotReadinessStopReason.STORE_SCOPE_MISMATCH),
    ],
)
def test_missing_or_foreign_product_identity_holds(
    product_update: dict[str, object],
    expected: PilotReadinessStopReason,
) -> None:
    products = list(_products())
    products[0] = products[0].model_copy(update=product_update)

    report = build_pilot_data_readiness_report(
        store_id=STORE,
        products=tuple(products),
        credential_read_only=True,
        approved_product_names=PRODUCT_NAMES,
    )

    assert report.shopify_lane.status is PilotLaneStatus.HOLD
    assert expected.value in report.shopify_lane.rejected_reasons


def test_report_contains_no_secret_or_source_text() -> None:
    report = build_pilot_data_readiness_report(
        store_id=STORE,
        products=_products(),
        credential_read_only=False,
        approved_product_names=PRODUCT_NAMES,
    )
    wire = report.to_wire()
    assert "token" not in str(wire).lower()
    assert "password" not in str(wire).lower()
    assert "source_text" not in str(wire).lower()
