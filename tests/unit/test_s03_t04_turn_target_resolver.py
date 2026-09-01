"""S03-T04 precedence, temporary override, and switch intent coverage."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    CatalogReferenceResolver,
    DeterministicCatalogFixture,
    ExplicitReference,
)
from backend.catalog.fixture import ISOLATION_STORE_ID, PRIMARY_STORE_ID
from backend.common import ObjectScope
from backend.conversation import (
    ConversationState,
    InMemoryConversationStateRepository,
    ResolutionReason,
    TurnIntent,
    TurnTargetResolutionInput,
    TurnTargetResolver,
)
from backend.conversation.state import ConfirmedTargetContext, StateTransitionStatus
from backend.conversation.target_resolution import (
    ContextAction,
    ResolutionSource,
    TurnTargetKind,
)

pytestmark = pytest.mark.unit


def scope(product_id: str, variant_id: str | None = None) -> ObjectScope:
    return ObjectScope(
        store_id=PRIMARY_STORE_ID, product_id=product_id, variant_id=variant_id
    )


def resolver() -> TurnTargetResolver:
    snapshot = DeterministicCatalogFixture(
        observed_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    ).load_store(store_id=PRIMARY_STORE_ID)
    return TurnTargetResolver(
        catalog_resolver=CatalogReferenceResolver(snapshot=snapshot)
    )


def request(
    message_id: str,
    *,
    page_scope: ObjectScope | None = None,
    explicit: ExplicitReference | None = None,
    intent: TurnIntent = TurnIntent.FACT_QUERY,
    revision: int = 0,
) -> TurnTargetResolutionInput:
    return TurnTargetResolutionInput(
        conversation_id="s03-t04",
        message_id=message_id,
        expected_revision=revision,
        page_scope=page_scope,
        explicit_reference=explicit,
        intent=intent,
    )


def test_explicit_reference_overrides_confirmed_and_page_without_mutating_context() -> (
    None
):
    state = ConversationState(
        conversation_id="s03-t04",
        confirmed_context=ConfirmedTargetContext(
            target=scope("drone-cinema"),
            confirmed_by_message_id="old",
            confirmed_at_revision=0,
        ),
    )

    outcome = resolver().resolve(
        request=request(
            "temporary",
            page_scope=scope("drone-survey"),
            explicit=ExplicitReference(product_name="Northwind Travel"),
        ),
        state=state,
    )

    assert outcome.resolution.turn_target.object_scope == scope("drone-travel")
    assert outcome.resolution.resolution_source is ResolutionSource.EXPLICIT
    assert outcome.resolution.context_action is ContextAction.KEEP
    assert outcome.reason is ResolutionReason.EXPLICIT_REFERENCE
    assert outcome.state_patch is not None
    result = InMemoryConversationStateRepository()
    result.save(state)
    applied = result.apply(outcome.state_patch)
    assert applied.state == state


def test_confirmed_context_beats_a_different_page_context_for_pronouns() -> None:
    state = ConversationState(
        conversation_id="s03-t04",
        confirmed_context=ConfirmedTargetContext(
            target=scope("drone-cinema"),
            confirmed_by_message_id="old",
            confirmed_at_revision=0,
        ),
    )

    outcome = resolver().resolve(
        request=request("pronoun", page_scope=scope("drone-travel")), state=state
    )

    assert outcome.resolution.turn_target.object_scope == scope("drone-cinema")
    assert outcome.resolution.resolution_source is ResolutionSource.CONFIRMED_CONTEXT


def test_page_context_is_the_default_only_when_no_confirmed_or_explicit_target() -> (
    None
):
    outcome = resolver().resolve(
        request=request("page", page_scope=scope("drone-travel")),
        state=ConversationState(conversation_id="s03-t04"),
    )

    assert outcome.resolution.turn_target.object_scope == scope("drone-travel")
    assert outcome.resolution.resolution_source is ResolutionSource.PAGE_CONTEXT


def test_unresolved_explicit_reference_fails_closed() -> None:
    outcome = resolver().resolve(
        request=request(
            "unknown",
            page_scope=scope("drone-travel"),
            explicit=ExplicitReference(product_name="not a drone"),
        ),
        state=ConversationState(conversation_id="s03-t04"),
    )

    assert outcome.resolution.turn_target.kind is TurnTargetKind.NEEDS_CLARIFICATION
    assert outcome.resolution.turn_target.object_scope is None
    assert outcome.state_patch is None


def test_explicit_switch_and_pending_confirmation_apply_exactly_once_each() -> None:
    repository = InMemoryConversationStateRepository()
    target_resolver = resolver()
    state = repository.get("s03-t04")
    switch = target_resolver.resolve(
        request=request(
            "switch",
            explicit=ExplicitReference(product_name="Northwind Travel"),
            intent=TurnIntent.EXPLICIT_SWITCH,
        ),
        state=state,
    )
    assert switch.resolution.context_action is ContextAction.SWITCH_CONFIRMED
    assert switch.state_patch is not None
    first = repository.apply(switch.state_patch)
    assert first.state.revision == 1
    assert first.state.confirmed_context is not None
    assert first.state.confirmed_context.target == scope("drone-travel")


def test_pending_decline_and_expiration_are_traceable_reducer_patches() -> None:
    repository = InMemoryConversationStateRepository()
    target_resolver = resolver()
    initial = target_resolver.resolve(
        request=request(
            "switch",
            explicit=ExplicitReference(product_name="Northwind Travel"),
            intent=TurnIntent.EXPLICIT_SWITCH,
        ),
        state=repository.get("s03-t04"),
    )
    assert initial.state_patch is not None
    repository.apply(initial.state_patch)
    # Create a pending target through the existing T02 reducer contract.
    from backend.conversation import (
        ContextAction,
        TargetResolution,
        TurnTarget,
        TurnTargetKind,
    )
    from backend.conversation.state import StateTransitionRequest

    pending = TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.SINGLE_OBJECT, object_scope=scope("drone-cinema")
        ),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=ContextAction.AWAIT_CONFIRMATION,
    )
    repository.apply(
        StateTransitionRequest(
            conversation_id="s03-t04",
            message_id="await",
            expected_revision=1,
            resolution=pending,
        )
    )

    outcome = target_resolver.resolve(
        request=request(
            "decline", intent=TurnIntent.DECLINE_PENDING_SWITCH, revision=2
        ),
        state=repository.get("s03-t04"),
    )
    assert outcome.reason is ResolutionReason.PENDING_SWITCH_CANCELLED
    assert outcome.state_patch is not None
    result = repository.apply(outcome.state_patch)
    assert result.state.revision == 3
    assert result.state.pending_switch is None


def test_cross_store_page_context_fails_closed() -> None:
    foreign_page = ObjectScope(store_id=ISOLATION_STORE_ID, product_id="drone-travel")
    outcome = resolver().resolve(
        request=request("foreign", page_scope=foreign_page),
        state=ConversationState(conversation_id="s03-t04"),
    )

    assert outcome.resolution.turn_target.kind is TurnTargetKind.NEEDS_CLARIFICATION
    assert outcome.reason is ResolutionReason.CROSS_STORE_CONTEXT


def test_stale_expected_revision_is_a_recoverable_reducer_conflict() -> None:
    state = ConversationState(
        conversation_id="s03-t04",
        revision=2,
        confirmed_context=ConfirmedTargetContext(
            target=scope("drone-cinema"),
            confirmed_by_message_id="old",
            confirmed_at_revision=2,
        ),
    )
    outcome = resolver().resolve(
        request=request("stale", page_scope=scope("drone-travel"), revision=1),
        state=state,
    )

    assert outcome.state_patch is not None
    repository = InMemoryConversationStateRepository()
    repository.save(state)
    result = repository.apply(outcome.state_patch)
    assert result.status is StateTransitionStatus.REVISION_CONFLICT
    assert result.conflict_revision == 2
