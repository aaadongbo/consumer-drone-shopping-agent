"""Unit coverage for current commerce Evidence conversion."""

from datetime import UTC, datetime

import pytest

from backend.catalog.fixture import PRIMARY_STORE_ID, DeterministicCatalogFixture
from backend.common import AttributeStatus, AttributeValue, ToolResult, ToolStatus
from backend.evidence import CandidateIdentity, build_commerce_evidence

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _candidate() -> CandidateIdentity:
    return CandidateIdentity(
        store_id=PRIMARY_STORE_ID, product_id="drone-travel", variant_id="travel-pack"
    )


def test_error_result_never_becomes_commerce_evidence() -> None:
    result = ToolResult[dict](
        status=ToolStatus.ERROR,
        source="fixture://store-s02-alpha/drone-travel/travel-pack",
        observed_at=_NOW,
        error_code="TIMEOUT",
        retryable=True,
    )
    assert build_commerce_evidence(candidate=_candidate(), result=result) == ()


def test_fact_observation_must_match_current_tool_result() -> None:
    fact = AttributeValue(
        status=AttributeStatus.KNOWN,
        value=4999,
        source_ref="fixture://price",
        observed_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    result = ToolResult[dict](
        status=ToolStatus.SUCCESS,
        data={"price": fact},
        source="fixture://store-s02-alpha/drone-travel/travel-pack",
        observed_at=_NOW,
        retryable=False,
    )
    with pytest.raises(ValueError, match="timestamp"):
        build_commerce_evidence(candidate=_candidate(), result=result)


def test_fact_source_must_match_its_field() -> None:
    snapshot = DeterministicCatalogFixture(observed_at=_NOW).load_store(
        store_id=PRIMARY_STORE_ID
    )
    result = next(
        item.result for item in snapshot.commerce if item.variant_id == "travel-pack"
    )
    assert result.data is not None
    bad_price = result.data["price"].model_copy(
        update={"source_ref": f"{result.source}#inventory"}
    )
    bad_result = result.model_copy(update={"data": {**result.data, "price": bad_price}})

    with pytest.raises(ValueError, match="source"):
        build_commerce_evidence(candidate=_candidate(), result=bad_result)
