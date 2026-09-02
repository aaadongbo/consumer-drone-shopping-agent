"""S04-T05 typed-handoff to internal comparison answer journeys."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.application import (
    ComparisonAnswerOutcome,
    ComparisonApplicationService,
    ComparisonTraceEventType,
)
from backend.catalog import CatalogFixtureSnapshot
from backend.common import (
    ObjectScope,
    TraceOperation,
)
from backend.conversation import (
    ComparisonMember,
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
    TypedHandoff,
    TypedHandoffRouter,
)
from backend.shopify import DeterministicShopifyFixture, FixtureOutcome

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
STORE_ID = "store-drone-cn"
PRODUCT_ID = "drone-mini"
CATALOG_REVISION = "catalog-s04-fixture-v1"


def _catalog_snapshot() -> CatalogFixtureSnapshot:
    source = DeterministicShopifyFixture(clock=lambda: NOW)
    products = []
    variants = []
    for product_id in ("drone-mini", "drone-cine"):
        product_result = source.get_products(store_id=STORE_ID, product_id=product_id)
        variant_result = source.get_variants(store_id=STORE_ID, product_id=product_id)
        assert product_result.data is not None
        assert variant_result.data is not None
        products.extend(product_result.data)
        variants.extend(variant_result.data)
    return CatalogFixtureSnapshot(
        store_id=STORE_ID,
        products=tuple(products),
        variants=tuple(variants),
        commerce=(),
    )


def _target(*members: tuple[str, ResolutionSource]) -> TurnTarget:
    return TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=tuple(
            ComparisonMember(
                scope=ObjectScope(
                    store_id=STORE_ID,
                    product_id=PRODUCT_ID,
                    variant_id=variant_id,
                ),
                provenance=source,
            )
            for variant_id, source in members
        ),
    )


def _handoff(target: TurnTarget) -> TypedHandoff:
    return TypedHandoffRouter().route(
        TargetResolution(turn_target=target, context_action=ContextAction.KEEP)
    )


def _service(
    shopify: DeterministicShopifyFixture | None = None,
    *,
    snapshot: CatalogFixtureSnapshot | None = None,
) -> ComparisonApplicationService:
    return ComparisonApplicationService(
        snapshot=snapshot or _catalog_snapshot(),
        shopify=shopify or DeterministicShopifyFixture(clock=lambda: NOW),
        catalog_revision=CATALOG_REVISION,
        clock=lambda: NOW,
        correlation_id_factory=lambda: "s04-t05-integration",
    )


def test_two_variant_handoff_produces_member_scoped_rows_and_trace() -> None:
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)
    answer = _service(shopify).answer(
        _handoff(
            _target(
                ("mini-standard", ResolutionSource.EXPLICIT),
                ("mini-explorer", ResolutionSource.EXPLICIT),
            )
        )
    )

    assert answer.outcome is ComparisonAnswerOutcome.ANSWER
    assert answer.comparison_set is not None
    assert answer.disclosure is not None
    assert [member.scope.variant_id for member in answer.disclosure.members] == [
        "mini-standard",
        "mini-explorer",
    ]
    rows = {row.field_key: row for row in answer.rows}
    assert rows["price"].cells[0].value == 2999
    assert rows["price"].cells[1].value == 4399
    assert rows["price"].difference is not None
    assert rows["obstacle_sensing"].cells[0].state.value == "UNKNOWN"
    assert rows["obstacle_sensing"].cells[0].value is None
    assert {cell.evidence_id for row in answer.rows for cell in row.cells}
    assert {event.correlation_id for event in answer.trace.events} == {
        answer.correlation_id
    }
    assert {event.event_type for event in answer.trace.events} >= {
        ComparisonTraceEventType.HANDOFF_RECEIVED,
        ComparisonTraceEventType.MEMBER_RESOLVED,
        ComparisonTraceEventType.STATIC_FACTS_BOUND,
        ComparisonTraceEventType.DYNAMIC_FACTS_BOUND,
        ComparisonTraceEventType.ANSWER_PRODUCED,
    }
    assert [entry.variant_id for entry in shopify.call_ledger] == [
        "mini-standard",
        "mini-explorer",
    ]
    assert shopify.write_call_count == 0


def test_confirmed_context_member_is_disclosed_without_state_mutation() -> None:
    answer = _service().answer(
        _handoff(
            _target(
                ("mini-standard", ResolutionSource.EXPLICIT),
                ("mini-explorer", ResolutionSource.CONFIRMED_CONTEXT),
            )
        ),
        confirmed_context_revision=12,
        correlation_id="s04-t05-confirmed",
    )

    assert answer.outcome is ComparisonAnswerOutcome.ANSWER
    assert answer.disclosure is not None
    confirmed = answer.disclosure.members[1]
    assert confirmed.provenance.source_kind.value == "CONFIRMED_CONTEXT"
    assert confirmed.provenance.context_revision == 12
    assert all(
        event.provenance is not None
        for event in answer.trace.events
        if event.event_type is ComparisonTraceEventType.MEMBER_RESOLVED
    )


def test_product_only_member_falls_back_before_dynamic_reads() -> None:
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            ComparisonMember(
                scope=ObjectScope(
                    store_id=STORE_ID,
                    product_id=PRODUCT_ID,
                ),
                provenance=ResolutionSource.EXPLICIT,
            ),
            ComparisonMember(
                scope=ObjectScope(
                    store_id=STORE_ID,
                    product_id=PRODUCT_ID,
                    variant_id="mini-explorer",
                ),
                provenance=ResolutionSource.EXPLICIT,
            ),
        ),
    )
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)

    answer = _service(shopify).answer(_handoff(target))

    assert answer.outcome is ComparisonAnswerOutcome.FALLBACK
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "PRODUCT_ONLY_REFERENCE"
    assert shopify.call_ledger == ()


def test_cross_product_handoff_is_typed_fallback_before_dynamic_reads() -> None:
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            ComparisonMember(
                scope=ObjectScope(
                    store_id=STORE_ID,
                    product_id="drone-mini",
                    variant_id="mini-standard",
                ),
                provenance=ResolutionSource.EXPLICIT,
            ),
            ComparisonMember(
                scope=ObjectScope(
                    store_id=STORE_ID,
                    product_id="drone-cine",
                    variant_id="cine-standard",
                ),
                provenance=ResolutionSource.EXPLICIT,
            ),
        ),
    )
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)

    answer = _service(shopify).answer(_handoff(target))

    assert answer.outcome is ComparisonAnswerOutcome.FALLBACK
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "CROSS_PRODUCT_DEFERRED"
    assert answer.fallback.next_actions
    assert shopify.call_ledger == ()


def test_dynamic_failure_keeps_rows_unavailable_and_actionable() -> None:
    shopify = DeterministicShopifyFixture(
        clock=lambda: NOW,
        forced_outcomes={TraceOperation.REFRESH_COMMERCE_STATE: FixtureOutcome.TIMEOUT},
    )
    answer = _service(shopify).answer(
        _handoff(
            _target(
                ("mini-standard", ResolutionSource.EXPLICIT),
                ("mini-explorer", ResolutionSource.EXPLICIT),
            )
        )
    )

    assert answer.outcome is ComparisonAnswerOutcome.DEGRADED
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "DYNAMIC_FACT_UNAVAILABLE"
    dynamic_rows = {
        row.field_key: row
        for row in answer.rows
        if row.field_key in {"price", "inventory", "availability"}
    }
    assert dynamic_rows
    assert all(
        cell.state.value == "UNAVAILABLE"
        and cell.value is None
        and cell.freshness is not None
        for row in dynamic_rows.values()
        for cell in row.cells
    )
    assert shopify.write_call_count == 0


def test_missing_static_evidence_falls_back_without_dynamic_read() -> None:
    snapshot = _catalog_snapshot()
    first = snapshot.variants[0]
    stripped = first.model_copy(
        update={
            "variant_attributes": {
                key: value
                for key, value in first.variant_attributes.items()
                if key != "takeoff_weight"
            }
        }
    )
    broken_snapshot = replace(
        snapshot,
        variants=(stripped, *snapshot.variants[1:]),
    )
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)

    answer = _service(shopify, snapshot=broken_snapshot).answer(
        _handoff(
            _target(
                ("mini-standard", ResolutionSource.EXPLICIT),
                ("mini-explorer", ResolutionSource.EXPLICIT),
            )
        )
    )

    assert answer.outcome is ComparisonAnswerOutcome.FALLBACK
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "EVIDENCE_MISSING"
    assert shopify.call_ledger == ()
