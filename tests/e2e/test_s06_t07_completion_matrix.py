"""Slice 6 completion matrix over the multi-product recommendation flow."""

from datetime import UTC, datetime

import pytest

from backend.application import MultiProductRecommendationService
from backend.catalog import DeterministicCatalogFixture
from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import (
    SCHEMA_VERSION,
    ConversationRef,
    PageContext,
    ToolResult,
    TurnRequest,
)
from backend.evidence import (
    CandidateEvidence,
    CandidateEvidenceBundle,
    CandidateIdentity,
    CoverageStatus,
    EvidenceCoverage,
    EvidenceSourceKind,
)
from backend.shopify import CommerceState

pytestmark = pytest.mark.e2e

_NOW = datetime(2026, 9, 3, tzinfo=UTC)
_STORE_ID = "store-s02-alpha"


class _ReadOnlyCommerce:
    def __init__(self) -> None:
        self.snapshot: CatalogFixtureSnapshot = DeterministicCatalogFixture(
            observed_at=_NOW
        ).load_store(store_id=_STORE_ID)
        self.write_calls = 0

    def refresh_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ToolResult[CommerceState]:
        for item in self.snapshot.commerce:
            if (item.store_id, item.product_id, item.variant_id) == (
                store_id,
                product_id,
                variant_id,
            ):
                return item.result
        raise AssertionError("candidate scope crossed store/product/variant")


def _request(text: str) -> TurnRequest:
    return TurnRequest(
        schema_version=SCHEMA_VERSION,
        store_id=_STORE_ID,
        conversation=ConversationRef(conversation_id="s06-matrix", message_id=text),
        user_text=text,
        locale="zh-CN",
        page_context=PageContext(product_id="drone-travel"),
    )


def _run(text: str):
    port = _ReadOnlyCommerce()
    service = MultiProductRecommendationService(
        catalog=DeterministicCatalogFixture(observed_at=_NOW),
        shopify=port,
        correlation_id_factory=lambda: "s06-matrix-trace",
        clock=lambda: _NOW,
    )
    return service.recommend(_request(text)), port


def test_matrix_01_and_11_candidate_cap_and_deterministic_replay() -> None:
    first, _ = _run("预算 6000 元，适合旅行")
    second, _ = _run("预算 6000 元，适合旅行")

    assert first.fallback is None
    assert 1 <= len(first.candidates) <= 3
    assert len({item.candidate.product_id for item in first.candidates}) == len(
        first.candidates
    )
    assert first.to_wire() == second.to_wire()


def test_matrix_02_and_08_hard_constraints_and_unknown_are_fail_closed() -> None:
    no_match, port = _run("预算 1 元")
    assert no_match.candidates == ()
    assert no_match.fallback is not None
    assert no_match.fallback.reason.value == "NO_MATCH"
    assert port.write_calls == 0

    unknown_hard, _ = _run("重量 200 克")
    assert unknown_hard.candidates == ()
    assert unknown_hard.fallback is not None


def test_matrix_03_06_07_and_12_evidence_identity_derived_and_trace() -> None:
    result, port = _run("预算 6000 元，适合旅行")
    assert result.fallback is None
    assert port.write_calls == 0
    assert all(event.correlation_id == result.correlation_id for event in result.trace)
    for item in result.candidates:
        candidate = item.candidate
        bundle = item.evidence_bundle
        assert bundle.candidate == candidate
        assert all(
            evidence.candidate == candidate for evidence in bundle.catalog_evidence
        )
        assert all(
            evidence.candidate == candidate for evidence in bundle.commerce_evidence
        )
        assert all(
            derived.candidate == candidate for derived in bundle.derived_evidence
        )
        assert all(
            set(derived.input_evidence_ids)
            <= {
                evidence.evidence_id
                for evidence in (
                    *bundle.catalog_evidence,
                    *bundle.commerce_evidence,
                    *bundle.rag_evidence,
                )
            }
            for derived in bundle.derived_evidence
        )


def test_matrix_04_and_10_missing_dynamic_or_rag_data_has_no_stale_claim() -> None:
    result, _ = _run("当前价格和手册说明")
    assert result.fallback is None
    for item in result.candidates:
        assert any(
            evidence.field == "price"
            for evidence in item.evidence_bundle.commerce_evidence
        )
        assert item.evidence_bundle.rag_evidence == ()


def test_matrix_05_budget_margin_is_derived_from_current_price() -> None:
    result, _ = _run("预算 6000 元")
    for item in result.candidates:
        derived = item.evidence_bundle.derived_evidence
        assert derived
        assert derived[0].field == "budget_margin"
        assert derived[0].formula == "budget - current_price"


def test_matrix_07_foreign_evidence_is_rejected_before_explanation() -> None:
    candidate = CandidateIdentity(
        store_id=_STORE_ID, product_id="drone-travel", variant_id="travel-lite"
    )
    foreign = CandidateIdentity(
        store_id=_STORE_ID, product_id="drone-cinema", variant_id="cinema-pro"
    )
    evidence = CandidateEvidence(
        evidence_id="foreign-evidence",
        source_kind=EvidenceSourceKind.CATALOG,
        candidate=foreign,
        field="camera_resolution",
        fact=None,
        text="5.1K",
        source_ref="fixture://foreign",
    )
    with pytest.raises(ValueError, match="crossed candidate identity"):
        CandidateEvidenceBundle(
            candidate=candidate,
            catalog_evidence=(evidence,),
            coverage=EvidenceCoverage(status=CoverageStatus.MISSING),
        )


def test_matrix_09_trace_contains_candidate_decision_records() -> None:
    result, _ = _run("预算 6000 元")
    event_types = {event.event_type.value for event in result.trace}
    assert "CANDIDATE_SELECTED" in event_types
    assert "EVIDENCE_COLLECTED" in event_types
    assert "EXPLANATION_BUILT" in event_types
