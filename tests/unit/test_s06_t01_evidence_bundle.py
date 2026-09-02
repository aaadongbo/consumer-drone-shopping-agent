"""Unit coverage for the Slice 6 per-candidate evidence bundle."""

from datetime import UTC, datetime

import pytest

from backend.common import AttributeStatus, AttributeValue, ObjectScope
from backend.evidence import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    CoverageStatus,
    EvidenceCoverage,
    EvidenceSourceKind,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _candidate(variant_id: str = "travel-pack") -> CandidateIdentity:
    return CandidateIdentity(
        store_id="store-s02-alpha", product_id="drone-travel", variant_id=variant_id
    )


def _fact(value: object, source_ref: str = "fixture://fact") -> AttributeValue:
    return AttributeValue(
        status=AttributeStatus.KNOWN,
        value=value,
        source_ref=source_ref,
        observed_at=_NOW,
    )


def _coverage(*fields: str) -> EvidenceCoverage:
    return EvidenceCoverage(
        status=CoverageStatus.COMPLETE,
        required_fields=fields,
        covered_fields=fields,
    )


def _evidence(
    candidate: CandidateIdentity,
    *,
    evidence_id: str,
    kind: EvidenceSourceKind,
    field: str,
    value: object,
) -> CandidateEvidence:
    return CandidateEvidence(
        evidence_id=evidence_id,
        source_kind=kind,
        candidate=candidate,
        field=field,
        fact=_fact(value, f"fixture://{kind.value.lower()}/{field}"),
        source_ref=f"fixture://{kind.value.lower()}/{field}",
        observed_at=_NOW if kind is EvidenceSourceKind.COMMERCE else None,
    )


def test_bundle_keeps_each_evidence_lane_and_scope() -> None:
    candidate = _candidate()
    bundle = CandidateEvidenceBundle(
        candidate=candidate,
        catalog_evidence=(
            _evidence(
                candidate,
                evidence_id="catalog-weight",
                kind=EvidenceSourceKind.CATALOG,
                field="takeoff_weight",
                value=253,
            ),
        ),
        commerce_evidence=(
            _evidence(
                candidate,
                evidence_id="commerce-price",
                kind=EvidenceSourceKind.COMMERCE,
                field="price",
                value=4999,
            ),
        ),
        rag_evidence=(
            _evidence(
                candidate,
                evidence_id="rag-package",
                kind=EvidenceSourceKind.RAG,
                field="package_list",
                value="three batteries",
            ),
        ),
        coverage=_coverage("takeoff_weight", "price", "package_list"),
    )

    assert bundle.candidate == candidate
    assert bundle.commerce_evidence[0].observed_at == _NOW
    assert [item.source_kind for item in bundle.rag_evidence] == [
        EvidenceSourceKind.RAG
    ]


def test_candidate_identity_requires_a_concrete_variant() -> None:
    with pytest.raises(ValueError, match="concrete variant"):
        CandidateIdentity.from_scope(
            ObjectScope(store_id="store-s02-alpha", product_id="drone-travel")
        )


def test_bundle_rejects_foreign_candidate_evidence() -> None:
    candidate = _candidate()
    with pytest.raises(ValueError, match="crossed candidate identity"):
        CandidateEvidenceBundle(
            candidate=candidate,
            catalog_evidence=(
                _evidence(
                    _candidate("travel-lite"),
                    evidence_id="foreign",
                    kind=EvidenceSourceKind.CATALOG,
                    field="takeoff_weight",
                    value=249,
                ),
            ),
            coverage=EvidenceCoverage(status=CoverageStatus.MISSING),
        )


def test_bundle_rejects_duplicate_ids_and_unknown_derived_inputs() -> None:
    candidate = _candidate()
    shared = _evidence(
        candidate,
        evidence_id="duplicate",
        kind=EvidenceSourceKind.CATALOG,
        field="takeoff_weight",
        value=253,
    )
    with pytest.raises(ValueError, match="unique"):
        CandidateEvidenceBundle(
            candidate=candidate,
            catalog_evidence=(shared,),
            rag_evidence=(shared,),
            coverage=EvidenceCoverage(status=CoverageStatus.MISSING),
        )
