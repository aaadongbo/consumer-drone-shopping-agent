"""Integration boundary for per-candidate explanation coverage."""

import pytest

from backend.agent import build_recommendation_explanation
from backend.common import AttributeStatus, AttributeValue
from backend.evidence import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    CoverageStatus,
    EvidenceCoverage,
    EvidenceSourceKind,
)

pytestmark = pytest.mark.integration


def test_missing_noncritical_reason_does_not_remove_other_candidate_reason() -> None:
    candidate = CandidateIdentity(
        store_id="store-drone-cn", product_id="drone-cine", variant_id="cine-standard"
    )
    bundle = CandidateEvidenceBundle(
        candidate=candidate,
        catalog_evidence=(
            CandidateEvidence(
                evidence_id="camera",
                source_kind=EvidenceSourceKind.CATALOG,
                candidate=candidate,
                field="camera_resolution",
                fact=AttributeValue(
                    status=AttributeStatus.KNOWN,
                    value="5.1K",
                    source_ref="fixture://camera",
                ),
                source_ref="fixture://camera",
            ),
        ),
        coverage=EvidenceCoverage(
            status=CoverageStatus.PARTIAL,
            required_fields=("camera_resolution", "flight_time"),
            covered_fields=("camera_resolution",),
            missing_fields=("flight_time",),
        ),
    )
    result = build_recommendation_explanation(
        bundle, requested_fields=("camera_resolution", "flight_time")
    )
    assert result.explanation is not None
    assert [reason.field for reason in result.explanation.supported_reasons] == [
        "camera_resolution"
    ]
