"""Safe, in-memory aggregation of existing summary-only trace events."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from backend.common import ObjectScope, TraceEvent

_SENSITIVE_VALUE = re.compile(
    r"(?i)(authorization|bearer|api[_-]?key|credential|password|secret|token|"
    r"cookie|set-cookie|stack|traceback|exception|payload|sk-[a-z0-9_-]+)"
)


class TraceRedactionResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class TraceRedactionError(ValueError):
    """Raised instead of emitting a record when a sensitive value is attempted."""


@dataclass(frozen=True)
class TraceEventSummary:
    event_type: str
    result: str
    scope: ObjectScope | None
    operation: str | None
    tool_status: str | None
    fallback_reason: str | None


@dataclass(frozen=True)
class TraceTurnRecord:
    """A single correlation's safe, non-persistent trace projection."""

    correlation_id: str
    events: tuple[TraceEventSummary, ...]
    redaction_result: TraceRedactionResult = TraceRedactionResult.ACCEPTED


def aggregate_trace_turn(events: Iterable[TraceEvent]) -> TraceTurnRecord:
    """Aggregate exactly one existing trace correlation, rejecting unsafe input.

    This boundary deliberately accepts only the existing summary contract.  It
    has no payload, header, credential, or exception-stack parameters and does
    not write to a log, service, or persistent store.
    """

    supplied = tuple(events)
    if not supplied:
        raise TraceRedactionError("trace aggregation requires at least one event")

    correlation_id = supplied[0].correlation_id
    if any(event.correlation_id != correlation_id for event in supplied):
        raise TraceRedactionError("trace aggregation requires one correlation")

    _assert_safe(correlation_id)
    summaries: list[TraceEventSummary] = []
    for event in supplied:
        summary = event.summary
        _assert_safe_scope(summary.scope)
        _assert_safe_values(
            event.event_type.value,
            summary.result.value,
            summary.operation.value if summary.operation else None,
            summary.tool_status.value if summary.tool_status else None,
            summary.fallback_reason.value if summary.fallback_reason else None,
        )
        summaries.append(
            TraceEventSummary(
                event_type=event.event_type.value,
                result=summary.result.value,
                scope=summary.scope,
                operation=summary.operation.value if summary.operation else None,
                tool_status=summary.tool_status.value if summary.tool_status else None,
                fallback_reason=(
                    summary.fallback_reason.value if summary.fallback_reason else None
                ),
            )
        )
    return TraceTurnRecord(correlation_id=correlation_id, events=tuple(summaries))


def _assert_safe_scope(scope: ObjectScope | None) -> None:
    if scope is not None:
        _assert_safe_values(scope.store_id, scope.product_id, scope.variant_id)


def _assert_safe_values(*values: str | None) -> None:
    for value in values:
        if value is not None:
            _assert_safe(value)


def _assert_safe(value: str) -> None:
    if _SENSITIVE_VALUE.search(value):
        raise TraceRedactionError("unsafe trace value rejected")
