"""Unit coverage for explicit Slice 10 fixture/pilot composition."""

from datetime import UTC, datetime

import pytest

from backend.agent import IntentAdapterSignal, IntentRoute, IntentSignalStatus
from backend.application import (
    PilotCompositionConfig,
    PilotCompositionError,
    PilotMode,
    build_pilot_composition,
)
from backend.catalog import (
    PilotDataReadinessReport,
    PilotLaneReport,
    PilotLaneStatus,
    PilotProductIdentity,
    PilotReadinessStopReason,
    PilotVariantIdentity,
)
from backend.common import ConversationRef, PageContext, TurnRequest
from backend.shopify import (
    DeterministicShopifyFixture,
    RealShopifyReadAdapter,
    ShopifyTransportResult,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 7, 0, tzinfo=UTC)
STORE = "store-dji-cn"


class EmptyTransport:
    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        return ShopifyTransportResult(payload={})

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        return ShopifyTransportResult(payload={})

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        return ShopifyTransportResult(payload={})


class EmptyRetriever:
    def retrieve(self, request):
        raise AssertionError("the composition test must not retrieve")


class StaticRetriever:
    def retrieve(self, request):
        raise AssertionError("safe fallback must not retrieve")


class FakeIntentAdapter:
    def __init__(self, signal: IntentAdapterSignal) -> None:
        self.signal = signal

    def route(self, request, *, budget):
        assert budget.max_model_tokens > 0
        return self.signal


def fixture() -> DeterministicShopifyFixture:
    return DeterministicShopifyFixture(clock=lambda: NOW)


def live_adapter() -> RealShopifyReadAdapter:
    return RealShopifyReadAdapter(
        transport=EmptyTransport(),
        clock=lambda: NOW,
        approved_store_id=STORE,
        approved_variant_ids={"p1": "v1"},
    )


def ready_report() -> PilotDataReadinessReport:
    products = tuple(
        PilotProductIdentity(
            product_name=name,
            store_id=STORE,
            product_id=product_id,
            variants=(
                PilotVariantIdentity(
                    store_id=STORE,
                    product_id=product_id,
                    variant_id=variant_id,
                ),
            ),
        )
        for name, product_id, variant_id in (
            ("DJI Air 3", "p1", "v1"),
            ("DJI Mavic 3", "p2", "v2"),
            ("DJI Mini 3", "p3", "v3"),
        )
    )
    lane = PilotLaneReport(
        status=PilotLaneStatus.GO,
        stop_reason=PilotReadinessStopReason.READY,
        accepted_product_count=3,
        accepted_variant_count=3,
    )
    return PilotDataReadinessReport(
        store_id=STORE,
        approved_product_names=tuple(item.product_name for item in products),
        shopify_lane=lane,
        corpus_lane=lane,
        accepted_products=products,
        accepted_variant_ids=tuple(item.variants[0].variant_id for item in products),
    )


def config(**overrides):
    values = {
        "mode": PilotMode.FIXTURE,
        "store_id": STORE,
        "shopify": fixture(),
        "static_retriever": EmptyRetriever(),
    }
    values.update(overrides)
    return PilotCompositionConfig(**values)


def test_fixture_mode_selects_only_the_configured_fixture_adapter() -> None:
    source = fixture()
    composition = build_pilot_composition(config(shopify=source, mode="fixture"))

    assert composition.mode is PilotMode.FIXTURE
    assert composition.shopify is source
    assert composition.store_id == STORE
    assert composition.application is not None
    assert composition.api is not None


def test_pilot_mode_requires_ready_metadata_and_live_adapter() -> None:
    composition = build_pilot_composition(
        config(
            mode=PilotMode.PILOT,
            shopify=live_adapter(),
            readiness=ready_report(),
        )
    )

    assert composition.mode is PilotMode.PILOT
    assert isinstance(composition.shopify, RealShopifyReadAdapter)


@pytest.mark.parametrize(
    "overrides",
    [
        {"mode": PilotMode.PILOT, "shopify": fixture(), "readiness": ready_report()},
        {"mode": PilotMode.FIXTURE, "shopify": live_adapter()},
        {"mode": PilotMode.PILOT, "shopify": live_adapter()},
        {
            "mode": PilotMode.PILOT,
            "shopify": live_adapter(),
            "readiness": ready_report().model_copy(update={"store_id": "foreign"}),
        },
    ],
)
def test_invalid_mode_or_readiness_fails_closed(overrides: dict[str, object]) -> None:
    with pytest.raises(PilotCompositionError):
        build_pilot_composition(config(**overrides))


def test_unaccepted_readiness_and_incomplete_scope_are_rejected() -> None:
    report = ready_report().model_copy(
        update={
            "shopify_lane": PilotLaneReport(
                status=PilotLaneStatus.HOLD,
                stop_reason=PilotReadinessStopReason.READ_ONLY_CREDENTIAL_REQUIRED,
                accepted_product_count=0,
                accepted_variant_count=0,
                rejected_reasons=("READ_ONLY_CREDENTIAL_REQUIRED",),
            )
        }
    )

    with pytest.raises(PilotCompositionError):
        build_pilot_composition(
            config(mode=PilotMode.PILOT, shopify=live_adapter(), readiness=report)
        )


def test_missing_dependencies_and_unknown_mode_are_rejected_without_fallback() -> None:
    with pytest.raises(PilotCompositionError):
        build_pilot_composition(config(shopify=None))
    with pytest.raises(PilotCompositionError):
        build_pilot_composition(config(mode="unknown"))


def test_intent_adapter_can_only_force_safe_fallback_not_answer_generation() -> None:
    composition = build_pilot_composition(
        config(
            shopify=fixture(),
            static_retriever=StaticRetriever(),
            intent_adapter=FakeIntentAdapter(
                IntentAdapterSignal(
                    status=IntentSignalStatus.UNSUPPORTED_INTENT,
                    route=IntentRoute.SAFE_FALLBACK,
                    confidence=1.0,
                )
            ),
        )
    )

    response = composition.application.answer(
        TurnRequest(
            schema_version="1.0",
            store_id=STORE,
            conversation=ConversationRef(
                conversation_id="conversation-1",
                message_id="message-1",
            ),
            user_text="包装里有什么？",
            locale="zh-CN",
            page_context=PageContext(product_id="p1", variant_id="v1"),
        )
    )

    assert response.root.outcome.value == "FALLBACK"


def test_unsupported_commerce_route_is_converted_to_safe_fallback() -> None:
    composition = build_pilot_composition(
        config(
            shopify=fixture(),
            static_retriever=StaticRetriever(),
            intent_adapter=FakeIntentAdapter(
                IntentAdapterSignal(
                    status=IntentSignalStatus.ROUTED,
                    route=IntentRoute.COMMERCE_FACT,
                    confidence=1.0,
                )
            ),
        )
    )

    response = composition.application.answer(
        TurnRequest(
            schema_version="1.0",
            store_id=STORE,
            conversation=ConversationRef(
                conversation_id="conversation-1",
                message_id="message-1",
            ),
            user_text="这款现在库存如何？",
            locale="zh-CN",
            page_context=PageContext(product_id="p1", variant_id="v1"),
        )
    )

    assert response.root.outcome.value == "FALLBACK"
