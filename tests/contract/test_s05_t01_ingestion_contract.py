"""S05-T01 contract coverage for internal Product RAG manifest shape."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.rag import DocumentManifest, DocumentSource, DocumentSourceType

pytestmark = pytest.mark.contract

_FIXTURE = (
    Path(__file__).parents[2] / "eval" / "datasets" / "s05_authorized_product_docs.json"
)


def test_manifest_fixture_round_trips_through_internal_schema() -> None:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )

    assert DocumentManifest.model_validate(manifest.to_wire()) == manifest
    assert manifest.source_by_id("drone-travel-faq") is not None


def test_document_source_requires_strict_manifest_fields() -> None:
    source = DocumentSource(
        store_id="store-s02-alpha",
        product_id="drone-travel",
        source_id="drone-travel-faq",
        source_type=DocumentSourceType.FAQ,
        version="docs-2026-09-01",
        canonical_locator="rag://drone-travel-faq@docs-2026-09-01/faq",
        authorization_state="AUTHORIZED",
        title="FAQ",
        text="Authorized static product facts.",
    )

    assert source.variant_id is None
    assert source.locator("faq/q1").locator.endswith("/faq/q1")

    with pytest.raises(ValidationError):
        DocumentSource.model_validate({**source.to_wire(), "unexpected": "field"})


def test_locator_prefix_binds_source_id_and_version() -> None:
    manifest = DocumentManifest.model_validate_json(
        _FIXTURE.read_text(encoding="utf-8")
    )
    source = manifest.sources[0]

    with pytest.raises(ValidationError, match="canonical_locator"):
        DocumentSource.model_validate(
            {
                **source.to_wire(),
                "canonical_locator": "rag://other@docs-2026-09-01/faq",
            }
        )
    with pytest.raises(ValueError, match="locator path"):
        source.locator("")
