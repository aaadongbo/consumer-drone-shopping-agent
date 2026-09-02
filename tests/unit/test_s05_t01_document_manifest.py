"""S05-T01 unit coverage for authorized document manifests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.rag import (
    AuthorizationState,
    DocumentManifest,
    SourceLocator,
    build_authorized_manifest,
)

pytestmark = pytest.mark.unit

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def load_manifest() -> DocumentManifest:
    return DocumentManifest.model_validate_json(_FIXTURE.read_text(encoding="utf-8"))


def test_manifest_fixture_contains_only_authorized_single_product_sources() -> None:
    manifest = load_manifest()

    assert manifest.store_id == "store-s02-alpha"
    assert manifest.product_id == "drone-travel"
    assert manifest.variant_id is None
    assert len(manifest.sources) == 4
    assert {source.source_type for source in manifest.sources}
    assert {source.authorization_state for source in manifest.sources} == {
        AuthorizationState.AUTHORIZED
    }
    assert {
        (source.store_id, source.product_id, source.variant_id)
        for source in manifest.sources
    } == {("store-s02-alpha", "drone-travel", None)}


def test_source_locator_is_canonical_and_replayable() -> None:
    manifest = load_manifest()
    source = manifest.source_by_id("drone-travel-manual")
    assert source is not None

    locator = source.locator("manual/takeoff/step-1")

    assert locator == SourceLocator(
        source_id="drone-travel-manual",
        version="docs-2026-09-01",
        locator="rag://drone-travel-manual@docs-2026-09-01/manual/takeoff/step-1",
    )
    assert manifest.source_by_id(locator.source_id) == source


def test_manifest_rejects_unauthorized_sources() -> None:
    manifest = load_manifest()
    unsafe_source = manifest.sources[0].model_copy(
        update={"authorization_state": AuthorizationState.UNAUTHORIZED}
    )

    with pytest.raises(ValidationError, match="authorized"):
        build_authorized_manifest(
            manifest_id="unsafe",
            store_id=manifest.store_id,
            product_id=manifest.product_id,
            document_version=manifest.document_version,
            sources=(unsafe_source,),
        )


def test_manifest_rejects_cross_product_or_version_mismatch() -> None:
    manifest = load_manifest()
    wrong_product = manifest.sources[0].model_copy(
        update={"product_id": "drone-cinema"}
    )
    wrong_version = manifest.sources[1].model_copy(update={"version": "older-docs"})

    for source in (wrong_product, wrong_version):
        with pytest.raises(ValidationError):
            build_authorized_manifest(
                manifest_id="mismatch",
                store_id=manifest.store_id,
                product_id=manifest.product_id,
                document_version=manifest.document_version,
                sources=(source,),
            )


def test_serialized_manifest_contains_no_secret_customer_or_network_payload() -> None:
    wire = json.dumps(load_manifest().to_wire()).lower()

    prohibited = {
        "api_key",
        "authorization",
        "credential",
        "customer",
        "header",
        "password",
        "secret",
        "token",
    }
    assert prohibited.isdisjoint(wire.split())
    assert "http://" not in wire
    assert "https://" not in wire
