"""Unit coverage for evidence-backed recommendation explanations."""

import pytest

from backend.agent import (
    RecommendationFallbackReason,
    build_recommendation_explanation,
)
from backend.common import AttributeStatus, AttributeValue
from backend.evidence import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    CoverageStatus,
    EvidenceCoverage,
    EvidenceSourceKind,
)

pytestmark = pytest.mark.unit


def _candidate() -> CandidateIdentity:
    return CandidateIdentity(
        store_id="store-drone-cn", product_id="drone-travel", variant_id="travel-pack"
    )


def _bundle(*evidence: CandidateEvidence) -> CandidateEvidenceBundle:
    candidate = _candidate()
    return CandidateEvidenceBundle(
        candidate=candidate,
        catalog_evidence=tuple(
            item for item in evidence if item.source_kind is EvidenceSourceKind.CATALOG
        ),
        commerce_evidence=tuple(
            item for item in evidence if item.source_kind is EvidenceSourceKind.COMMERCE
        ),
        rag_evidence=tuple(
            item for item in evidence if item.source_kind is EvidenceSourceKind.RAG
        ),
        coverage=EvidenceCoverage(status=CoverageStatus.PARTIAL),
    )


def _evidence(field: str, value: object, evidence_id: str) -> CandidateEvidence:
    candidate = _candidate()
    return CandidateEvidence(
        evidence_id=evidence_id,
        source_kind=EvidenceSourceKind.RAG,
        candidate=candidate,
        field=field,
        fact=AttributeValue(
            status=AttributeStatus.KNOWN,
            value=value,
            source_ref=f"fixture://{field}",
        ),
        source_ref=f"fixture://{field}",
    )


def test_explanation_contains_only_bound_reasons() -> None:
    result = build_recommendation_explanation(
        _bundle(_evidence("package_list", "three batteries", "rag-package")),
        requested_fields=("package_list", "flight_time"),
    )
    assert result.explanation is not None
    assert [item.field for item in result.explanation.supported_reasons] == [
        "package_list"
    ]
    assert result.explanation.binding_map == {"package_list": ("rag-package",)}


def test_noncritical_unknown_is_disclosed_and_critical_missing_falls_back() -> None:
    unknown = _evidence("flight_time", 20, "unknown").model_copy(
        update={
            "fact": AttributeValue(
                status=AttributeStatus.UNKNOWN, source_ref="fixture://flight_time"
            )
        }
    )
    result = build_recommendation_explanation(
        _bundle(unknown), requested_fields=("flight_time",)
    )
    assert result.explanation is not None
    assert result.explanation.unknown_dimensions == ("flight_time",)

    fallback = build_recommendation_explanation(
        _bundle(), requested_fields=("price",), critical_fields=("price",)
    )
    assert fallback.fallback is not None
    assert (
        fallback.fallback.reason
        is RecommendationFallbackReason.COVERAGE_BELOW_THRESHOLD
    )
    assert fallback.fallback.candidate == _candidate()


def test_tradeoff_evidence_cannot_cross_candidate() -> None:
    foreign = CandidateIdentity(
        store_id="store-drone-cn", product_id="drone-cine", variant_id="cine-standard"
    )
    foreign_tradeoff = _evidence("price", 4999, "foreign").model_copy(
        update={"candidate": foreign}
    )
    with pytest.raises(ValueError, match="crossed candidate identity"):
        build_recommendation_explanation(
            _bundle(),
            requested_fields=(),
            tradeoffs=(foreign_tradeoff,),  # type: ignore[arg-type]
        )
