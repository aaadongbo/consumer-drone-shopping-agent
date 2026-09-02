"""Contract coverage for the internal Slice 6 evidence bundle shape."""

import pytest

from backend.common import AttributeStatus, AttributeValue
from backend.evidence import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    CoverageStatus,
    EvidenceCoverage,
    EvidenceSourceKind,
)

pytestmark = pytest.mark.contract


def test_bundle_round_trip_is_lossless_and_explicitly_version_free() -> None:
    candidate = CandidateIdentity(
        store_id="store-s02-alpha", product_id="drone-travel", variant_id="travel-pack"
    )
    bundle = CandidateEvidenceBundle(
        candidate=candidate,
        catalog_evidence=(
            CandidateEvidence(
                evidence_id="catalog-use-case",
                source_kind=EvidenceSourceKind.CATALOG,
                candidate=candidate,
                field="use_case",
                fact=AttributeValue(
                    status=AttributeStatus.KNOWN,
                    value="travel",
                    source_ref="fixture://catalog/use_case",
                ),
                source_ref="fixture://catalog/use_case",
            ),
        ),
        coverage=EvidenceCoverage(
            status=CoverageStatus.COMPLETE,
            required_fields=("use_case",),
            covered_fields=("use_case",),
        ),
    )

    wire = bundle.to_wire()
    restored = CandidateEvidenceBundle.model_validate(wire)
    assert restored == bundle
    assert "schema_version" not in wire


def test_commerce_evidence_requires_observation_timestamp() -> None:
    candidate = CandidateIdentity(
        store_id="store-s02-alpha", product_id="drone-travel", variant_id="travel-pack"
    )
    with pytest.raises(ValueError, match="observed_at"):
        CandidateEvidence(
            evidence_id="commerce-price",
            source_kind=EvidenceSourceKind.COMMERCE,
            candidate=candidate,
            field="price",
            fact=AttributeValue(
                status=AttributeStatus.KNOWN,
                value=4999,
                source_ref="fixture://commerce/price",
            ),
            source_ref="fixture://commerce/price",
        )
