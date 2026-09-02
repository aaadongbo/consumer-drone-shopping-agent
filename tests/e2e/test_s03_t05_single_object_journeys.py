"""S03-T05 end-to-end single-object target identity journeys."""

from datetime import UTC, datetime

import pytest

from backend.application import (
    DeterministicQuestionInterpreter,
    InMemoryTraceSink,
    Slice1ApplicationService,
)
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    ObjectScope,
    PageContext,
    TurnRequest,
)
from backend.conversation import (
    ContextAction,
    ResolutionSource,
    TargetResolution,
    TurnTarget,
    TurnTargetKind,
)
from backend.shopify.fixture import DeterministicShopifyFixture

pytestmark = pytest.mark.e2e


def test_cross_page_target_never_mixes_page_evidence() -> None:
    service = Slice1ApplicationService(
        shopify=DeterministicShopifyFixture(
            clock=lambda: datetime(2026, 9, 2, tzinfo=UTC)
        ),
        interpreter=DeterministicQuestionInterpreter(),
        trace_sink=InMemoryTraceSink(),
        correlation_id_factory=lambda: "s03-t05-e2e",
        clock=lambda: datetime(2026, 9, 2, tzinfo=UTC),
    )
    request = TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(conversation_id="t05-e2e", message_id="m1"),
        user_text="这款无人机的制造商是谁？",
        locale="zh-CN",
        page_context=PageContext(product_id="drone-mini"),
    )
    resolution = TargetResolution(
        turn_target=TurnTarget(
            kind=TurnTargetKind.SINGLE_OBJECT,
            object_scope=ObjectScope(
                store_id="store-drone-cn", product_id="drone-cine"
            ),
        ),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=ContextAction.KEEP,
    )

    payload = service.answer_resolved(request, resolution).root

    assert payload.resolved_scope.product_id == "drone-cine"
    assert payload.evidence[0].product_id == "drone-cine"
    assert payload.claims[0].fact == payload.evidence[0].fact
