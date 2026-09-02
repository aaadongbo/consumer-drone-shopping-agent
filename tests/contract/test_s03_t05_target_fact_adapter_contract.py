"""S03-T05 internal Target-to-Fact identity boundary contracts."""

import pytest

from backend.application import TargetFactIdentityAdapter, TargetFactIdentityError
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

pytestmark = pytest.mark.contract


def request() -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id="store-drone-cn",
        conversation=ConversationRef(conversation_id="t05", message_id="m1"),
        user_text="这款无人机的制造商是谁？",
        locale="zh-CN",
        page_context=PageContext(product_id="drone-mini"),
    )


def resolution(kind: TurnTargetKind, scope: ObjectScope | None) -> TargetResolution:
    if kind is not TurnTargetKind.SINGLE_OBJECT:
        return TargetResolution(
            turn_target=TurnTarget(
                kind=kind, clarification_reason="not a single target"
            ),
            context_action=ContextAction.KEEP,
        )
    return TargetResolution(
        turn_target=TurnTarget(kind=kind, object_scope=scope),
        resolution_source=ResolutionSource.EXPLICIT,
        context_action=ContextAction.KEEP,
    )


def test_adapter_forwards_only_the_resolved_scope_not_page_context() -> None:
    target = ObjectScope(store_id="store-drone-cn", product_id="drone-cine")

    assert (
        TargetFactIdentityAdapter().resolve_scope(
            request=request(),
            resolution=resolution(TurnTargetKind.SINGLE_OBJECT, target),
        )
        == target
    )


@pytest.mark.parametrize(
    "target",
    [
        resolution(TurnTargetKind.NEEDS_CLARIFICATION, None),
        resolution(
            TurnTargetKind.SINGLE_OBJECT,
            ObjectScope(store_id="foreign-store", product_id="drone-cine"),
        ),
    ],
)
def test_adapter_rejects_non_single_or_cross_store_target(
    target: TargetResolution,
) -> None:
    with pytest.raises(TargetFactIdentityError):
        TargetFactIdentityAdapter().resolve_scope(request=request(), resolution=target)
