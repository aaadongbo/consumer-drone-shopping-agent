"""Integration boundary for typed S05 retriever requests."""

import pytest

from backend.agent import (
    EvidenceObjective,
    PerProductEvidenceBudget,
    RecommendationActionPlan,
    build_retrieval_requests,
)
from backend.evidence import CandidateIdentity
from backend.rag import (
    AuthorizationState,
    DocumentManifest,
    DocumentSource,
    DocumentSourceType,
    InMemoryProductRetriever,
    chunk_manifest,
)

pytestmark = pytest.mark.integration


def test_each_candidate_request_is_accepted_by_existing_scoped_retriever() -> None:
    manifest = DocumentManifest(
        manifest_id="s06-manifest",
        store_id="store-s02-alpha",
        product_id="drone-travel",
        variant_id="travel-pack",
        document_version="s06-test",
        sources=(
            DocumentSource(
                store_id="store-s02-alpha",
                product_id="drone-travel",
                variant_id="travel-pack",
                source_id="s06-package",
                source_type=DocumentSourceType.PACKAGE_LIST,
                version="s06-test",
                canonical_locator="rag://s06-package@s06-test/source",
                authorization_state=AuthorizationState.AUTHORIZED,
                title="Package",
                text="Three batteries are included.",
            ),
        ),
    )
    retriever = InMemoryProductRetriever(
        chunk_manifest(manifest), index_version=manifest.document_version
    )
    candidate = CandidateIdentity(
        store_id="store-s02-alpha", product_id="drone-travel", variant_id="travel-pack"
    )
    plan = RecommendationActionPlan(
        candidate_set=(candidate,),
        evidence_objectives=(
            EvidenceObjective(
                candidate=candidate, field="package_list", question="What is included?"
            ),
        ),
        per_product_budgets=(PerProductEvidenceBudget(candidate=candidate),),
    )
    request = build_retrieval_requests(plan, {})[0]
    result = retriever.retrieve(request)
    assert result.request.turn_target == candidate.as_scope()
    assert len(result.evidence) == 1
    assert result.evidence[0].variant_id == candidate.variant_id
