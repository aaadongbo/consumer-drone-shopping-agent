"""S04-T06 completion matrix for the internal comparison boundary."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.application import (
    ComparisonAnswerOutcome,
    ComparisonApplicationService,
    ComparisonTraceEventType,
)
from backend.catalog import CatalogFixtureSnapshot, DeterministicCatalogFixture
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.common import AttributeStatus, ObjectScope, TraceOperation
from backend.conversation import (
    ComparisonSetResolver,
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
    TypedHandoff,
    TypedHandoffRouter,
)
from backend.conversation.target_resolution import (
    ComparisonMember as HandoffComparisonMember,
)
from backend.evidence import (
    ComparisonFact,
    ComparisonFactState,
    ComparisonFreshnessVerdict,
    build_static_comparison_facts,
)
from backend.shopify import DeterministicShopifyFixture, FixtureOutcome

pytestmark = pytest.mark.e2e

NOW = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
STORE_ID = "store-drone-cn"
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


def _handoff_member(
    variant_id: str | None,
    *,
    product_id: str = "drone-mini",
    store_id: str = STORE_ID,
    source: ResolutionSource = ResolutionSource.EXPLICIT,
) -> HandoffComparisonMember:
    return HandoffComparisonMember(
        scope=ObjectScope(
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
        ),
        provenance=source,
    )


def _target(*members: HandoffComparisonMember) -> TurnTarget:
    return TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=members,
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
        correlation_id_factory=lambda: "s04-t06-matrix",
    )


def _two_variant_target() -> TurnTarget:
    return _target(
        _handoff_member("mini-standard"),
        _handoff_member("mini-explorer"),
    )


def test_s4_a01_bounded_two_variant_set_enters_comparison() -> None:
    answer = _service().answer(_handoff(_two_variant_target()))

    assert answer.outcome is ComparisonAnswerOutcome.ANSWER
    assert answer.comparison_set is not None
    assert len(answer.comparison_set.members) == 2
    assert {member.scope.variant_id for member in answer.comparison_set.members} == {
        "mini-standard",
        "mini-explorer",
    }


def test_s4_a02_product_variant_identity_is_preserved_in_rows_and_differences() -> None:
    answer = _service().answer(
        _handoff(
            _target(
                _handoff_member("mini-standard"),
                _handoff_member("mini-explorer"),
            )
        )
    )

    assert answer.disclosure is not None
    assert all(member.scope.variant_id for member in answer.disclosure.members)
    assert all(
        cell.scope.variant_id in {"mini-standard", "mini-explorer"}
        for row in answer.rows
        for cell in row.cells
    )
    assert answer.differences
    assert all(
        {member.member_id for member in difference.members} == {"member-1", "member-2"}
        for difference in answer.differences
    )


def test_s4_a03_explicit_and_confirmed_provenance_are_disclosed_per_member() -> None:
    answer = _service().answer(
        _handoff(
            _target(
                _handoff_member("mini-standard"),
                _handoff_member(
                    "mini-explorer", source=ResolutionSource.CONFIRMED_CONTEXT
                ),
            )
        ),
        confirmed_context_revision=17,
    )

    assert answer.disclosure is not None
    assert [
        member.provenance.source_kind.value for member in answer.disclosure.members
    ] == [
        "EXPLICIT",
        "CONFIRMED_CONTEXT",
    ]
    assert answer.disclosure.members[1].provenance.context_revision == 17


def test_s4_a04_context_isolation_has_no_state_write_surface() -> None:
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)
    before = tuple(shopify.call_ledger)
    answer = _service(shopify).answer(
        _handoff(_two_variant_target()),
        confirmed_context_revision=4,
    )

    assert answer.outcome is ComparisonAnswerOutcome.ANSWER
    assert before == ()
    assert shopify.write_call_count == 0


def test_s4_a05_cross_product_scope_is_typed_deferral() -> None:
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)
    answer = _service(shopify).answer(
        _handoff(
            _target(
                _handoff_member("mini-standard"),
                _handoff_member("cine-standard", product_id="drone-cine"),
            )
        )
    )

    assert answer.outcome is ComparisonAnswerOutcome.FALLBACK
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "CROSS_PRODUCT_DEFERRED"
    assert shopify.call_ledger == ()


def test_s4_a06_unknown_and_not_applicable_states_remain_distinct() -> None:
    snapshot = DeterministicCatalogFixture(observed_at=NOW).load_store(
        store_id=PRIMARY_STORE_ID
    )
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            _handoff_member(
                "travel-lite",
                product_id="drone-travel",
                store_id=PRIMARY_STORE_ID,
            ),
            _handoff_member(
                "travel-pack",
                product_id="drone-travel",
                store_id=PRIMARY_STORE_ID,
            ),
        ),
    )
    resolved = ComparisonSetResolver(
        snapshot=snapshot,
        catalog_revision=CATALOG_REVISION,
    ).materialize(target=target, correlation_id="s04-t06-states")
    assert resolved.comparison_set is not None
    facts = build_static_comparison_facts(
        comparison_set=resolved.comparison_set,
        snapshot=snapshot,
        field_keys=("obstacle_sensing", "interchangeable_lens"),
    )
    states = {(fact.member_id, fact.field_key): fact.state for fact in facts.facts}

    assert states["member-1", "obstacle_sensing"] is AttributeStatus.UNKNOWN
    assert states["member-1", "interchangeable_lens"] is AttributeStatus.NOT_APPLICABLE


def test_s4_a07_cross_member_evidence_injection_is_rejected() -> None:
    snapshot = DeterministicCatalogFixture(observed_at=NOW).load_store(
        store_id=PRIMARY_STORE_ID
    )
    target = TurnTarget(
        kind=TurnTargetKind.COMPARISON_SET,
        comparison_members=(
            _handoff_member(
                "travel-lite",
                product_id="drone-travel",
                store_id=PRIMARY_STORE_ID,
            ),
            _handoff_member(
                "travel-pack",
                product_id="drone-travel",
                store_id=PRIMARY_STORE_ID,
            ),
        ),
    )
    resolved = ComparisonSetResolver(
        snapshot=snapshot,
        catalog_revision=CATALOG_REVISION,
    ).materialize(target=target, correlation_id="s04-t06-evidence")
    assert resolved.comparison_set is not None
    fact = build_static_comparison_facts(
        comparison_set=resolved.comparison_set,
        snapshot=snapshot,
        field_keys=("battery_count",),
    ).facts[0]

    with pytest.raises(ValidationError, match="match the fact member"):
        ComparisonFact(
            comparison_fact_id=fact.comparison_fact_id,
            member_id=fact.member_id,
            field_key=fact.field_key,
            fact=fact.fact,
            state=fact.state,
            source_class=fact.source_class,
            catalog_revision=fact.catalog_revision,
            binding=fact.binding.model_copy(update={"member_id": "member-2"}),
        )


def test_s4_a08_current_dynamic_reads_are_fresh_and_member_scoped() -> None:
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)
    answer = _service(shopify).answer(_handoff(_two_variant_target()))

    dynamic = [fact for fact in answer.dynamic_facts.facts]
    assert len(dynamic) == 6
    assert all(
        fact.state is AttributeStatus.KNOWN
        and fact.freshness is not None
        and fact.freshness.verdict is ComparisonFreshnessVerdict.FRESH
        for fact in dynamic
    )
    assert {(fact.member_id, fact.binding.scope.variant_id) for fact in dynamic} == {
        ("member-1", "mini-standard"),
        ("member-2", "mini-explorer"),
    }


def test_s4_a09_stale_dynamic_read_is_unavailable_with_next_action() -> None:
    shopify = DeterministicShopifyFixture(
        clock=lambda: NOW - timedelta(minutes=6),
    )
    answer = _service(shopify).answer(_handoff(_two_variant_target()))

    assert answer.outcome is ComparisonAnswerOutcome.DEGRADED
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "DYNAMIC_FACT_UNAVAILABLE"
    assert all(
        fact.state is ComparisonFactState.UNAVAILABLE
        and fact.fact.value is None
        and fact.freshness is not None
        and fact.freshness.verdict is ComparisonFreshnessVerdict.STALE
        for fact in answer.dynamic_facts.facts
    )
    assert answer.fallback.next_actions


def test_s4_a10_failed_dynamic_read_is_read_only_and_traceable() -> None:
    shopify = DeterministicShopifyFixture(
        clock=lambda: NOW,
        forced_outcomes={TraceOperation.REFRESH_COMMERCE_STATE: FixtureOutcome.TIMEOUT},
    )
    answer = _service(shopify).answer(_handoff(_two_variant_target()))

    assert answer.outcome is ComparisonAnswerOutcome.DEGRADED
    assert all(
        fact.state is ComparisonFactState.UNAVAILABLE and fact.fact.value is None
        for fact in answer.dynamic_facts.facts
    )
    assert shopify.write_call_count == 0
    assert {event.event_type for event in answer.trace.events} >= {
        ComparisonTraceEventType.DYNAMIC_FACTS_BOUND,
        ComparisonTraceEventType.ANSWER_PRODUCED,
    }


def test_s4_a11_trace_contains_full_correlation_chain_and_zero_writes() -> None:
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)
    answer = _service(shopify).answer(_handoff(_two_variant_target()))

    assert answer.correlation_id == "s04-t06-matrix"
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
    assert shopify.write_call_count == 0
    assert [entry.operation for entry in shopify.call_ledger] == [
        TraceOperation.REFRESH_COMMERCE_STATE,
        TraceOperation.REFRESH_COMMERCE_STATE,
    ]


def test_s4_a01_to_a05_invalid_bounds_never_select_default_variant() -> None:
    with pytest.raises(ValidationError, match="requires two to four"):
        _target(_handoff_member("mini-standard"))
    with pytest.raises(ValidationError, match="requires two to four"):
        _target(
            _handoff_member("mini-standard"),
            _handoff_member("mini-explorer"),
            _handoff_member("mini-standard-3"),
            _handoff_member("mini-standard-4"),
            _handoff_member("mini-standard-5"),
        )
    with pytest.raises(ValidationError, match="members must be unique"):
        _target(
            _handoff_member("mini-standard"),
            _handoff_member("mini-standard"),
        )
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)
    foreign = _target(
        _handoff_member("mini-standard", store_id="other-store"),
        _handoff_member("mini-explorer"),
    )
    answer = _service(shopify).answer(_handoff(foreign))
    assert answer.outcome is ComparisonAnswerOutcome.FALLBACK
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "CROSS_STORE"
    assert shopify.call_ledger == ()


def test_s4_a02_ownership_mismatch_fails_before_dynamic_reads() -> None:
    shopify = DeterministicShopifyFixture(clock=lambda: NOW)
    answer = _service(shopify).answer(
        _handoff(
            _target(
                _handoff_member("cine-standard"),
                _handoff_member("mini-explorer"),
            )
        )
    )

    assert answer.outcome is ComparisonAnswerOutcome.FALLBACK
    assert answer.fallback is not None
    assert answer.fallback.reason.value == "OWNERSHIP_MISMATCH"
    assert shopify.call_ledger == ()
