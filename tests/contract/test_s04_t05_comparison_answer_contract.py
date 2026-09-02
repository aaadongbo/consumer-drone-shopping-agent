"""S04-T05 internal answer/fallback contract round trips."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.application import ComparisonAnswer, ComparisonAnswerOutcome
from backend.common import AnswerEnvelope
from backend.conversation import (
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
    TypedHandoffRouter,
)
from tests.integration.test_s04_t05_comparison_flow import (
    _handoff,
    _service,
    _target,
)

pytestmark = pytest.mark.contract


def test_internal_answer_round_trip_does_not_expand_public_schema() -> None:
    answer = _service().answer(
        _handoff(
            _target(
                ("mini-standard", ResolutionSource.EXPLICIT),
                ("mini-explorer", ResolutionSource.EXPLICIT),
            )
        ),
        correlation_id="s04-t05-contract",
    )

    restored = ComparisonAnswer.model_validate_json(answer.to_wire_json())

    assert restored == answer
    assert restored.outcome is ComparisonAnswerOutcome.ANSWER
    assert restored.correlation_id == "s04-t05-contract"
    assert restored.comparison_set is not None
    assert restored.disclosure is not None
    assert restored.rows
    assert restored.differences
    assert {event.correlation_id for event in restored.trace.events} == {
        restored.correlation_id
    }

    public_schema = AnswerEnvelope.model_json_schema()
    assert "ComparisonAnswer" not in str(public_schema)
    assert "comparison_set" not in str(public_schema)


def test_fallback_contract_requires_actionable_next_action() -> None:
    handoff = TypedHandoffRouter().route(
        TargetResolution(
            turn_target=TurnTarget(
                kind=TurnTargetKind.NEEDS_CLARIFICATION,
                clarification_reason="member is ambiguous",
            ),
            context_action=ContextAction.KEEP,
        )
    )
    fallback = _service().answer(handoff, correlation_id="s04-t05-fallback")

    restored = ComparisonAnswer.model_validate_json(fallback.to_wire_json())

    assert restored.outcome is ComparisonAnswerOutcome.FALLBACK
    assert restored.fallback is not None
    assert restored.fallback.next_actions
    assert restored.comparison_set is None
    assert restored.rows == ()
    assert restored.differences == ()
    assert restored.static_facts.facts == ()
    assert restored.dynamic_facts.facts == ()


@pytest.mark.parametrize("tampered_field", ("value", "state", "source", "freshness"))
def test_tampered_row_cell_payload_is_rejected(tampered_field: str) -> None:
    answer = _service().answer(
        _handoff(
            _target(
                ("mini-standard", ResolutionSource.EXPLICIT),
                ("mini-explorer", ResolutionSource.EXPLICIT),
            )
        ),
        correlation_id=f"s04-t05-cell-{tampered_field}",
    )
    payload = deepcopy(answer.model_dump(mode="json", exclude_none=True))
    price_row = next(row for row in payload["rows"] if row["field_key"] == "price")
    cell = price_row["cells"][0]
    if tampered_field == "value":
        cell["value"] = 0
    elif tampered_field == "state":
        cell["state"] = "UNAVAILABLE"
        cell["value"] = None
        cell["freshness"] = "UNAVAILABLE"
    elif tampered_field == "source":
        cell["source_class"] = "CATALOG"
        cell.pop("freshness")
    else:
        cell["freshness"] = "UNAVAILABLE"

    with pytest.raises(ValidationError, match="row cell"):
        ComparisonAnswer.model_validate(payload)
