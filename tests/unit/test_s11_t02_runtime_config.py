"""S11-T02 unit coverage for config and composition fail-closed boundaries."""

from __future__ import annotations

import pytest

from backend.catalog import (
    PilotDataReadinessReport,
    PilotLaneReport,
    PilotLaneStatus,
    PilotProductIdentity,
    PilotReadinessStopReason,
)
from backend.runtime import (
    ReleaseConfig,
    ReleaseConfigError,
    ReleaseDependencies,
    build_closed_beta_composition,
)
from backend.shopify import DeterministicShopifyFixture, RealShopifyReadAdapter

pytestmark = pytest.mark.unit


class _NoopTransport:
    def request(self, **_kwargs):
        raise AssertionError("runtime config tests must not call Shopify")


class _NoopRetriever:
    def retrieve(self, _request):
        raise AssertionError("runtime config tests must not retrieve documents")


def _env(**overrides: str) -> dict[str, str]:
    values = {
        "DRONE_RELEASE_MODE": "closed_beta",
        "DRONE_ENVIRONMENT": "local",
        "DRONE_HOSTING_RUNTIME": "single_container",
        "DRONE_STORE_ID": "shopify-store:test",
        "DRONE_SHOPIFY_ADAPTER_MODE": "pilot_read_only",
        "DRONE_CREDENTIAL_REF": "keychain://shopify-read-only",
        "DRONE_KEYCHAIN_SERVICE": "consumer-drone-agent.shopify.smoke.access-token",
        "DRONE_WIDGET_ORIGINS": "https://beta.example.test",
        "DRONE_INTENT_ADAPTER_MODE": "deterministic",
        "DRONE_PILOT_READINESS_REF": "staging://pilot-readiness-v1",
        "DRONE_CORPUS_MANIFEST_REF": "staging://corpus-v0.1",
    }
    values.update(overrides)
    return values


def _readiness() -> PilotDataReadinessReport:
    lane = PilotLaneReport(
        status=PilotLaneStatus.GO,
        stop_reason=PilotReadinessStopReason.READY,
        accepted_product_count=3,
        accepted_variant_count=3,
    )
    return PilotDataReadinessReport(
        store_id="shopify-store:test",
        approved_product_names=("Mini 3", "Air 3", "Mavic 3"),
        shopify_lane=lane,
        corpus_lane=lane,
        accepted_products=(
            PilotProductIdentity(
                product_name="Mini 3",
                store_id="shopify-store:test",
                product_id="mini-3",
            ),
            PilotProductIdentity(
                product_name="Air 3",
                store_id="shopify-store:test",
                product_id="air-3",
            ),
            PilotProductIdentity(
                product_name="Mavic 3",
                store_id="shopify-store:test",
                product_id="mavic-3",
            ),
        ),
    )


def test_from_env_requires_explicit_closed_beta_configuration() -> None:
    config = ReleaseConfig.from_env(_env())

    assert config.release_mode == "closed_beta"
    assert config.max_action_rounds == 2
    assert config.max_shopify_read_calls_per_turn == 2
    metadata = config.safe_metadata()
    assert "credential_ref" not in metadata
    assert "keychain_service" not in metadata


@pytest.mark.parametrize(
    "changes",
    [
        {"DRONE_RELEASE_MODE": "fixture"},
        {"DRONE_WIDGET_ORIGINS": "*"},
        {"DRONE_KEYCHAIN_SERVICE": ""},
        {"DRONE_CREDENTIAL_REF": "token-value"},
        {"DRONE_MAX_ACTION_ROUNDS": "3"},
    ],
)
def test_unsafe_or_implicit_configuration_fails_closed(
    changes: dict[str, str],
) -> None:
    with pytest.raises((ReleaseConfigError, ValueError)):
        ReleaseConfig.from_env(_env(**changes))


def test_provider_mode_requires_provider_and_model_id() -> None:
    with pytest.raises((ReleaseConfigError, ValueError)):
        ReleaseConfig.from_env(_env(DRONE_INTENT_ADAPTER_MODE="provider"))

    config = ReleaseConfig.from_env(
        _env(
            DRONE_INTENT_ADAPTER_MODE="provider",
            DRONE_MODEL_PROVIDER="example",
            DRONE_MODEL_ID="bounded-test-model",
        )
    )
    assert config.model_provider == "example"


def test_hosted_runtime_requires_secret_store_and_never_keychain() -> None:
    with pytest.raises((ReleaseConfigError, ValueError)):
        ReleaseConfig.from_env(
            _env(
                DRONE_ENVIRONMENT="beta",
                DRONE_CREDENTIAL_REF="secret://shopify-read-only",
                DRONE_KEYCHAIN_SERVICE="consumer-drone-agent.shopify.smoke.access-token",
            )
        )

    config = ReleaseConfig.from_env(
        _env(
            DRONE_ENVIRONMENT="beta",
            DRONE_CREDENTIAL_REF="secret://shopify-read-only",
            DRONE_KEYCHAIN_SERVICE="",
            DRONE_SECRET_STORE_REF="hosted://beta-secrets/shopify",
        )
    )
    assert config.environment.value == "beta"


def test_closed_beta_composition_rejects_fixture_fallback() -> None:
    config = ReleaseConfig.from_env(_env())
    dependencies = ReleaseDependencies(
        shopify=DeterministicShopifyFixture(clock=lambda: None),
        static_retriever=_NoopRetriever(),
        readiness=_readiness(),
    )

    with pytest.raises(ReleaseConfigError, match="live read adapter"):
        build_closed_beta_composition(config, dependencies)


def test_closed_beta_composition_accepts_injected_read_only_adapter() -> None:
    config = ReleaseConfig.from_env(_env())
    adapter = RealShopifyReadAdapter(transport=_NoopTransport())
    composition = build_closed_beta_composition(
        config,
        ReleaseDependencies(
            shopify=adapter,
            static_retriever=_NoopRetriever(),
            readiness=_readiness(),
        ),
    )

    assert composition.mode.value == "pilot"
    assert composition.store_id == "shopify-store:test"
