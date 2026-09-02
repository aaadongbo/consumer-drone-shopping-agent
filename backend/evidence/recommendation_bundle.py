"""Internal per-candidate evidence bundle for Slice 6 recommendations.

The bundle is deliberately separate from the public Slice 1 ``Evidence``
contract.  Recommendation assembly needs to keep catalog, commerce, document
and derived provenance distinct until a later task composes a response.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, Field, JsonValue, StringConstraints, model_validator

from backend.common import AttributeValue, ObjectScope
from backend.common.contracts import WireModel

type NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class EvidenceSourceKind(StrEnum):
    """The source lane of one candidate-scoped fact."""

    CATALOG = "CATALOG"
    COMMERCE = "COMMERCE"
    RAG = "RAG"
    DERIVED = "DERIVED"


class CoverageStatus(StrEnum):
    """Coverage is explicit so missing evidence cannot look like a claim."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class CandidateIdentity(WireModel):
    """Immutable identity for one concrete recommended Variant."""

    store_id: NonEmptyString
    product_id: NonEmptyString
    variant_id: NonEmptyString

    @classmethod
    def from_scope(cls, scope: ObjectScope) -> "CandidateIdentity":
        if scope.variant_id is None:
            raise ValueError("Recommendation candidates require a concrete variant")
        return cls(
            store_id=scope.store_id,
            product_id=scope.product_id,
            variant_id=scope.variant_id,
        )

    def as_scope(self) -> ObjectScope:
        return ObjectScope(
            store_id=self.store_id,
            product_id=self.product_id,
            variant_id=self.variant_id,
        )


class CandidateEvidence(WireModel):
    """One source-backed fact or excerpt owned by exactly one candidate."""

    evidence_id: NonEmptyString
    source_kind: EvidenceSourceKind
    candidate: CandidateIdentity
    field: NonEmptyString
    fact: AttributeValue | None = None
    text: NonEmptyString | None = None
    source_ref: NonEmptyString
    observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "CandidateEvidence":
        if self.fact is None and self.text is None:
            raise ValueError("candidate evidence requires a fact or text")
        if self.source_kind is EvidenceSourceKind.COMMERCE and self.observed_at is None:
            raise ValueError("commerce evidence requires observed_at")
        return self


class EvidenceCoverage(WireModel):
    """Replayable coverage summary for one candidate evidence bundle."""

    status: CoverageStatus
    required_fields: tuple[NonEmptyString, ...] = ()
    covered_fields: tuple[NonEmptyString, ...] = ()
    missing_fields: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_fields(self) -> "EvidenceCoverage":
        required = set(self.required_fields)
        covered = set(self.covered_fields)
        missing = set(self.missing_fields)
        if not covered <= required:
            raise ValueError("covered fields must be required fields")
        if not missing <= required:
            raise ValueError("missing fields must be required fields")
        if covered & missing:
            raise ValueError("a field cannot be both covered and missing")
        if self.status is CoverageStatus.COMPLETE and (missing or covered != required):
            raise ValueError("complete coverage requires every required field")
        if self.status is CoverageStatus.MISSING and covered:
            raise ValueError("missing coverage cannot contain covered fields")
        return self


class DerivedEvidence(WireModel):
    """A later deterministic calculation bound to candidate evidence inputs."""

    evidence_id: NonEmptyString
    candidate: CandidateIdentity
    field: NonEmptyString
    value: JsonValue
    unit: NonEmptyString | None = None
    formula: NonEmptyString
    input_evidence_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    observed_at: AwareDatetime | None = None
    catalog_version: NonEmptyString | None = None


class CandidateEvidenceBundle(WireModel):
    """All evidence lanes for one candidate, with identity isolation enforced."""

    candidate: CandidateIdentity
    catalog_evidence: tuple[CandidateEvidence, ...] = ()
    commerce_evidence: tuple[CandidateEvidence, ...] = ()
    rag_evidence: tuple[CandidateEvidence, ...] = ()
    derived_evidence: tuple[DerivedEvidence, ...] = ()
    coverage: EvidenceCoverage

    @model_validator(mode="after")
    def validate_identity_and_ids(self) -> "CandidateEvidenceBundle":
        all_evidence = (
            *self.catalog_evidence,
            *self.commerce_evidence,
            *self.rag_evidence,
        )
        for item in all_evidence:
            if item.candidate != self.candidate:
                raise ValueError("candidate evidence crossed candidate identity")
        for item in self.derived_evidence:
            if item.candidate != self.candidate:
                raise ValueError("derived evidence crossed candidate identity")
        evidence_ids = [item.evidence_id for item in all_evidence]
        derived_ids = [item.evidence_id for item in self.derived_evidence]
        all_ids = evidence_ids + derived_ids
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("evidence IDs must be unique within a candidate bundle")
        available_ids = set(all_ids)
        if any(
            input_id not in available_ids
            for item in self.derived_evidence
            for input_id in item.input_evidence_ids
        ):
            raise ValueError("derived evidence references an unknown input evidence ID")
        return self


def candidate_scope(bundle: CandidateEvidenceBundle) -> ObjectScope:
    """Return the existing scope type without exposing a second identity source."""

    return bundle.candidate.as_scope()


__all__ = [
    "CandidateEvidence",
    "CandidateEvidenceBundle",
    "CandidateIdentity",
    "CoverageStatus",
    "DerivedEvidence",
    "EvidenceCoverage",
    "EvidenceSourceKind",
    "candidate_scope",
]
