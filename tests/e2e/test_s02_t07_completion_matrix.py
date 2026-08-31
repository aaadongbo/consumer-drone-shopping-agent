"""S02-T07 replayable completion matrix for single-turn recommendation."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.agent import Slice2RecommendationService, Slice2TraceSink
from backend.api import MinimalConversationClient, create_conversation_api
from backend.catalog import (
    CatalogFixtureSnapshot,
    DeterministicCatalogFixture,
    evaluate_store_eligibility,
    rank_eligible_variants_by_soft_preferences,
)
from backend.catalog.fixture import (
    ISOLATION_STORE_ID,
    PRIMARY_STORE_ID,
    CommerceState,
    VariantCommerceSnapshot,
)
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    EnvelopeOutcome,
    FallbackReasonCode,
    PageContext,
    ToolErrorCode,
    ToolResult,
    ToolStatus,
    TraceEventType,
    TurnRequest,
)
from backend.conversation import (
    ConstraintField,
    ConstraintHardness,
    ConstraintOperation,
    ConstraintOperator,
    ConstraintProvenance,
    NormalizedConstraint,
    normalize_constraint_patches,
    parse_constraint_patches,
)
from backend.evidence import build_recommendation_candidates

pytestmark = pytest.mark.e2e

OBSERVED_AT = datetime(2026, 8, 31, 16, 30, tzinfo=UTC)
CORRELATION_ID = "correlation-s02-t07"


class MatrixCatalog:
    def __init__(self, snapshot: CatalogFixtureSnapshot) -> None:
        self._snapshot = snapshot
        self.reads = 0
        self.write_call_count = 0

    def load_store(self, *, store_id: str) -> CatalogFixtureSnapshot:
        self.reads += 1
        assert store_id == self._snapshot.store_id
        return self._snapshot


def _snapshot(store_id: str = PRIMARY_STORE_ID) -> CatalogFixtureSnapshot:
    return DeterministicCatalogFixture(observed_at=OBSERVED_AT).load_store(
        store_id=store_id
    )


def _request(
    text: str,
    *,
    store_id: str = PRIMARY_STORE_ID,
    product_id: str = "drone-travel",
) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=store_id,
        conversation=ConversationRef(
            conversation_id="conversation-s02-t07",
            message_id="message-s02-t07",
        ),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id=product_id),
    )


def _client(
    snapshot: CatalogFixtureSnapshot | None = None,
) -> tuple[MinimalConversationClient, MatrixCatalog, Slice2TraceSink]:
    sink = Slice2TraceSink()
    catalog = MatrixCatalog(snapshot or _snapshot())
    service = Slice2RecommendationService(
        catalog=catalog,
        trace_sink=sink,
        correlation_id_factory=lambda: CORRELATION_ID,
        clock=lambda: OBSERVED_AT,
    )
    return (
        MinimalConversationClient(TestClient(create_conversation_api(service))),
        catalog,
        sink,
    )


def test_s2_a01_constraint_parse_and_unsupported_degrade_are_replayable() -> None:
    parsed = parse_constraint_patches(
        _request(
            "请推荐旅行用无人机，预算 3000 元，重量 250g 以内，至少1块电池，4K，要避障"
        )
    )
    normalized = normalize_constraint_patches(parsed)

    assert {item.field for item in normalized} == {
        ConstraintField.PRICE,
        ConstraintField.TAKEOFF_WEIGHT,
        ConstraintField.BATTERY_COUNT,
        ConstraintField.USE_CASE,
        ConstraintField.CAMERA_RESOLUTION,
        ConstraintField.OBSTACLE_SENSING,
    }
    assert {
        item.hardness
        for item in normalized
        if item.field
        in {
            ConstraintField.PRICE,
            ConstraintField.TAKEOFF_WEIGHT,
            ConstraintField.BATTERY_COUNT,
        }
    } == {ConstraintHardness.HARD}
    assert parse_constraint_patches(_request("你喜欢什么颜色？"))[0].operation is (
        ConstraintOperation.NO_CHANGE
    )


def test_s2_a02_a03_a10_hard_eligibility_is_variant_current_and_fail_closed() -> None:
    constraints = (
        _constraint(ConstraintField.PRICE, ConstraintOperator.LTE, 3000, "CNY"),
        _constraint(ConstraintField.TAKEOFF_WEIGHT, ConstraintOperator.LTE, 250, "g"),
        _constraint(
            ConstraintField.BATTERY_COUNT,
            ConstraintOperator.GTE,
            1,
            "battery",
        ),
    )

    results = evaluate_store_eligibility(snapshot=_snapshot(), constraints=constraints)
    by_variant = {item.variant_id: item for item in results}

    assert by_variant["travel-lite"].eligible is True
    assert by_variant["travel-lite"].observed_at == OBSERVED_AT
    assert by_variant["travel-pack"].eligible is False
    assert by_variant["cinema-pro"].eligible is False
    assert by_variant["survey-base"].eligible is False
    assert any(
        reason.field == "takeoff_weight"
        for reason in by_variant["survey-base"].rejection_reasons
    )


def test_s2_a04_a05_a09_a12_response_identity_and_evidence_contract() -> None:
    client, catalog, sink = _client()

    payload = client.ask(
        _request(
            "请推荐一款适合旅行的无人机，预算 3000 元，重量 250g 以内，至少1块电池"
        )
    ).root

    assert payload.outcome is EnvelopeOutcome.ANSWER
    identity = (
        payload.resolved_scope.store_id,
        payload.resolved_scope.product_id,
        payload.resolved_scope.variant_id,
    )
    assert identity == (PRIMARY_STORE_ID, "drone-travel", "travel-lite")
    assert payload.product_card is not None
    assert (
        payload.product_card.store_id,
        payload.product_card.product_id,
        payload.product_card.variant_id,
    ) == identity
    evidence_by_id = {item.evidence_id: item for item in payload.evidence}
    for evidence in payload.evidence:
        assert (evidence.store_id, evidence.product_id, evidence.variant_id) == identity
    for binding in payload.bindings:
        claim = next(
            item for item in payload.claims if item.claim_id == binding.claim_id
        )
        assert len(binding.evidence_ids) == 1
        assert evidence_by_id[binding.evidence_ids[0]].fact == claim.fact
    assert payload.trace_correlation_id == CORRELATION_ID
    assert {event.correlation_id for event in sink.events} == {CORRELATION_ID}
    assert catalog.write_call_count == 0


def test_s2_a06_a07_a13_candidate_cap_order_and_replay_are_stable() -> None:
    snapshot = _snapshot()
    constraints = normalize_constraint_patches(
        parse_constraint_patches(_request("适合旅行，4K，要避障"))
    )

    first = _candidate_ids(snapshot, constraints)
    second = _candidate_ids(snapshot, constraints)

    assert first == second
    assert len(first) == 3
    assert len({product_id for product_id, _variant_id in first}) == 3
    assert first == (
        ("drone-travel", "travel-lite"),
        ("drone-cinema", "cinema-pro"),
        ("drone-survey", "survey-base"),
    )


def test_s2_a08_no_match_fallback_has_no_recommendation_claims() -> None:
    client, catalog, sink = _client()

    payload = client.ask(_request("预算 1000 元以内，至少3块电池，适合旅行")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.fallback.reason_code is FallbackReasonCode.FACT_UNKNOWN_OR_MISSING
    assert payload.claims == payload.evidence == payload.bindings == []
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }
    assert catalog.write_call_count == 0


def test_s2_a11_store_isolation_and_mismatched_store_fail_closed() -> None:
    client, catalog, _sink = _client(_snapshot(ISOLATION_STORE_ID))

    isolated = client.ask(
        _request(
            "请推荐一款适合旅行的无人机，预算 3000 元，至少1块电池",
            store_id=ISOLATION_STORE_ID,
        )
    ).root

    assert isolated.outcome is EnvelopeOutcome.ANSWER
    assert isolated.resolved_scope.store_id == ISOLATION_STORE_ID
    assert isolated.product_card is not None
    assert isolated.product_card.display_title == "Contoso Travel"
    assert all(item.store_id == ISOLATION_STORE_ID for item in isolated.evidence)
    assert catalog.write_call_count == 0

    leaky_snapshot = replace(_snapshot(), store_id=ISOLATION_STORE_ID)
    rejected = (
        _client(leaky_snapshot)[0]
        .ask(
            _request(
                "请推荐一款适合旅行的无人机，预算 3000 元，至少1块电池",
                store_id=ISOLATION_STORE_ID,
            )
        )
        .root
    )

    assert rejected.outcome is EnvelopeOutcome.FALLBACK
    assert rejected.claims == rejected.evidence == rejected.bindings == []
    assert rejected.resolved_scope.store_id == ISOLATION_STORE_ID


def test_s2_tool_error_fails_closed_without_answer() -> None:
    client, _catalog, sink = _client(_commerce_error_snapshot())

    payload = client.ask(_request("请推荐一款适合旅行的无人机，预算 3000 元")).root

    assert payload.outcome is EnvelopeOutcome.FALLBACK
    assert payload.claims == payload.evidence == payload.bindings == []
    assert TraceEventType.ANSWER_PRODUCED not in {
        event.event_type for event in sink.events
    }


def _constraint(
    field: ConstraintField,
    operator: ConstraintOperator,
    value: int,
    unit: str,
) -> NormalizedConstraint:
    return NormalizedConstraint(
        source_turn_id="message-s02-t07",
        field=field,
        operator=operator,
        value=value,
        unit=unit,
        hardness=ConstraintHardness.HARD,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
    )


def _candidate_ids(
    snapshot: CatalogFixtureSnapshot,
    constraints: tuple[NormalizedConstraint, ...],
) -> tuple[tuple[str, str], ...]:
    eligibility = evaluate_store_eligibility(snapshot=snapshot, constraints=constraints)
    scores = rank_eligible_variants_by_soft_preferences(
        snapshot=snapshot,
        eligibility_results=eligibility,
        constraints=constraints,
    )
    candidates = build_recommendation_candidates(
        snapshot=snapshot,
        eligibility_results=eligibility,
        soft_scores=scores,
    )
    return tuple((item.product_id, item.variant_id) for item in candidates.candidates)


def _commerce_error_snapshot() -> CatalogFixtureSnapshot:
    snapshot = _snapshot()
    commerce = tuple(
        VariantCommerceSnapshot(
            store_id=entry.store_id,
            product_id=entry.product_id,
            variant_id=entry.variant_id,
            result=ToolResult[CommerceState](
                status=ToolStatus.ERROR,
                source=entry.result.source,
                observed_at=OBSERVED_AT,
                error_code=ToolErrorCode.TIMEOUT,
                retryable=True,
            ),
        )
        for entry in snapshot.commerce
    )
    return CatalogFixtureSnapshot(
        store_id=snapshot.store_id,
        products=snapshot.products,
        variants=snapshot.variants,
        commerce=commerce,
    )
