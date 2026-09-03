from datetime import UTC, datetime

import pytest

from backend.common import (
    SCHEMA_VERSION,
    ObjectScope,
    TraceEvent,
    TraceEventType,
    TraceResult,
    TraceSummary,
)
from backend.evaluation import (
    TraceRedactionError,
    TraceRedactionResult,
    aggregate_trace_turn,
)

pytestmark = pytest.mark.unit


def _event(
    correlation_id: str = "s07-turn-1", *, scope: ObjectScope | None = None
) -> TraceEvent:
    return TraceEvent(
        schema_version=SCHEMA_VERSION,
        correlation_id=correlation_id,
        event_type=TraceEventType.ROUTE_DECISION,
        occurred_at=datetime(2026, 9, 3, tzinfo=UTC),
        summary=TraceSummary(result=TraceResult.SUCCESS, scope=scope),
    )


def test_aggregates_one_correlation_using_existing_summary_only_events() -> None:
    record = aggregate_trace_turn(
        [_event(), _event(scope=ObjectScope(store_id="s1", product_id="p1"))]
    )

    assert record.correlation_id == "s07-turn-1"
    assert record.redaction_result is TraceRedactionResult.ACCEPTED
    assert [event.event_type for event in record.events] == ["ROUTE_DECISION"] * 2
    assert record.events[1].scope == ObjectScope(store_id="s1", product_id="p1")


@pytest.mark.parametrize(
    "event",
    [
        _event("Bearer secret-token"),
        _event(scope=ObjectScope(store_id="s1", product_id="api_key=leak")),
    ],
)
def test_sensitive_correlation_or_scope_is_rejected_without_a_record(
    event: TraceEvent,
) -> None:
    with pytest.raises(TraceRedactionError, match="unsafe trace value rejected"):
        aggregate_trace_turn([event])


def test_mixed_correlations_fail_closed() -> None:
    with pytest.raises(TraceRedactionError, match="one correlation"):
        aggregate_trace_turn([_event("a"), _event("b")])


def test_empty_input_fails_closed() -> None:
    with pytest.raises(TraceRedactionError, match="at least one"):
        aggregate_trace_turn([])
