"""Contract-shaped serialization checks for the internal S10 readiness report."""

import pytest

from backend.catalog import (
    PilotDataReadinessReport,
    PilotLaneStatus,
    PilotProductIdentity,
    PilotReadinessStopReason,
    build_pilot_data_readiness_report,
)

pytestmark = pytest.mark.contract


def test_readiness_report_round_trips_without_public_contract_change() -> None:
    report = build_pilot_data_readiness_report(
        store_id="store-dji-cn",
        products=(
            PilotProductIdentity(
                product_name="DJI Mini 3",
                store_id="store-dji-cn",
                product_id="mini-3",
            ),
        ),
        credential_read_only=None,
        approved_product_names=("DJI Mini 3",),
    )
    payload = report.to_wire()
    restored = PilotDataReadinessReport.model_validate(payload)

    assert restored.shopify_lane.status is PilotLaneStatus.HOLD
    assert (
        restored.shopify_lane.stop_reason is PilotReadinessStopReason.PILOT_SCOPE_LIMIT
    )
    assert restored.model_dump(mode="json") == payload
