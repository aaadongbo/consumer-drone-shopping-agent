"""Contract-level serialization coverage for recommendation degradation."""

import pytest

from backend.agent import RecommendationFallback, RecommendationFallbackReason
from backend.evidence import CandidateIdentity

pytestmark = pytest.mark.contract


def test_fallback_is_internal_and_round_trips_without_public_envelope() -> None:
    fallback = RecommendationFallback(
        reason=RecommendationFallbackReason.RAG_UNAVAILABLE,
        candidate=CandidateIdentity(
            store_id="store-drone-cn",
            product_id="drone-travel",
            variant_id="travel-pack",
        ),
        missing_fields=("package_list",),
        message="Recommendation evidence is unavailable.",
    )
    assert RecommendationFallback.model_validate(fallback.to_wire()) == fallback
    assert "outcome" not in fallback.to_wire()
