"""S03-T04 multi-turn resolver/reducer integration journeys."""

from datetime import UTC, datetime

import pytest

from backend.catalog import (
    CatalogReferenceResolver,
    DeterministicCatalogFixture,
    ExplicitReference,
)
from backend.catalog.fixture import PRIMARY_STORE_ID
from backend.common import ObjectScope
from backend.conversation import (
    InMemoryConversationStateRepository,
    TurnTargetResolutionInput,
    TurnTargetResolver,
)

pytestmark = pytest.mark.integration


def test_temporary_cross_product_question_does_not_pollute_later_page_default() -> None:
    catalog = DeterministicCatalogFixture(
        observed_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    ).load_store(store_id=PRIMARY_STORE_ID)
    target_resolver = TurnTargetResolver(
        catalog_resolver=CatalogReferenceResolver(snapshot=catalog)
    )
    repository = InMemoryConversationStateRepository()
    state = repository.get("multi-turn")

    temporary = target_resolver.resolve(
        request=TurnTargetResolutionInput(
            conversation_id="multi-turn",
            message_id="m1",
            expected_revision=0,
            page_scope=ObjectScope(
                store_id=PRIMARY_STORE_ID, product_id="drone-cinema"
            ),
            explicit_reference=ExplicitReference(product_name="Northwind Travel"),
        ),
        state=state,
    )
    assert temporary.state_patch is not None
    assert repository.apply(temporary.state_patch).state.revision == 0

    follow_up = target_resolver.resolve(
        request=TurnTargetResolutionInput(
            conversation_id="multi-turn",
            message_id="m2",
            expected_revision=0,
            page_scope=ObjectScope(
                store_id=PRIMARY_STORE_ID, product_id="drone-cinema"
            ),
        ),
        state=repository.get("multi-turn"),
    )
    assert follow_up.resolution.turn_target.object_scope == ObjectScope(
        store_id=PRIMARY_STORE_ID, product_id="drone-cinema"
    )
