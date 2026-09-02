"""S04-T01 comparison identity and provenance contracts."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.common import ObjectScope, TurnRequest
from backend.conversation import (
    ComparisonScopeStatus,
    ComparisonSet,
    ComparisonSetMember,
    MemberProvenance,
    MemberSourceKind,
)

pytestmark = pytest.mark.contract

STORE_ID = "store-drone-cn"
APPROVED_VARIANT_MAPPING = {
    "51492095623306": "9278439686282",
    "51492157456522": "9278460821642",
    "51492095721610": "9278439719050",
}
APPROVED_VARIANT_IDS = tuple(APPROVED_VARIANT_MAPPING)
_GOLDEN = (
    Path(__file__).parents[1] / "fixtures" / ("s04_t01_comparison_contract_golden.json")
)


def scope(variant_id: str) -> ObjectScope:
    return ObjectScope(
        store_id=STORE_ID,
        product_id=APPROVED_VARIANT_MAPPING[variant_id],
        variant_id=variant_id,
    )


def explicit_member(member_id: str, variant_id: str) -> ComparisonSetMember:
    return ComparisonSetMember(
        member_id=member_id,
        scope=scope(variant_id),
        provenance=MemberProvenance(
            source_kind=MemberSourceKind.EXPLICIT,
            original_reference=f"variant:{variant_id}",
            resolver_outcome="unique_variant_reference",
        ),
        resolution_reason="explicit variant resolved by approved S04 mapping",
        catalog_revision="s04-planning-baseline-5af0296",
        display_name=f"Variant {variant_id}",
    )


def context_member(member_id: str, variant_id: str) -> ComparisonSetMember:
    return ComparisonSetMember(
        member_id=member_id,
        scope=scope(variant_id),
        provenance=MemberProvenance(
            source_kind=MemberSourceKind.CONFIRMED_CONTEXT,
            context_revision=7,
            resolver_outcome="confirmed_context_variant",
        ),
        resolution_reason="confirmed single-object context admitted as one member",
        catalog_revision="s04-planning-baseline-5af0296",
        display_name=f"Confirmed {variant_id}",
    )


def comparison_set(*members: ComparisonSetMember) -> ComparisonSet:
    return ComparisonSet(
        correlation_id="cmp-s04-t01-001",
        store_id=STORE_ID,
        members=members,
    )


def test_comparison_set_serializes_member_identity_and_provenance() -> None:
    comparison = comparison_set(
        explicit_member("member-a", APPROVED_VARIANT_IDS[0]),
        context_member("member-b", APPROVED_VARIANT_IDS[1]),
    )

    restored = ComparisonSet.model_validate_json(comparison.to_wire_json())

    assert restored == comparison
    assert restored.source_intent == "COMPARISON_SET"
    assert restored.members[0].scope.variant_id == "51492095623306"
    assert restored.members[1].provenance.source_kind is (
        MemberSourceKind.CONFIRMED_CONTEXT
    )
    assert {member.member_id for member in restored.members} == {
        "member-a",
        "member-b",
    }


def test_golden_fixture_is_serializable_and_uses_only_approved_variant_mapping() -> (
    None
):
    rows = json.loads(_GOLDEN.read_text(encoding="utf-8"))

    comparisons = [
        ComparisonSet.model_validate(row["expected_comparison_set"]) for row in rows
    ]

    assert [row["case_id"] for row in rows] == [
        "two-explicit-variants",
        "explicit-plus-confirmed-context-variant",
        "typed-fallback-cross-product",
    ]
    for comparison in comparisons:
        assert (
            ComparisonSet.model_validate_json(comparison.to_wire_json()) == comparison
        )
        for member in comparison.members:
            assert member.scope.variant_id in APPROVED_VARIANT_MAPPING
            assert (
                member.scope.product_id
                == APPROVED_VARIANT_MAPPING[member.scope.variant_id]
            )


def test_comparison_set_accepts_only_bounded_unique_variant_members() -> None:
    with pytest.raises(ValidationError, match="two to four"):
        comparison_set(explicit_member("member-a", APPROVED_VARIANT_IDS[0]))

    valid_three = comparison_set(
        explicit_member("member-a", APPROVED_VARIANT_IDS[0]),
        explicit_member("member-b", APPROVED_VARIANT_IDS[1]),
        explicit_member("member-c", APPROVED_VARIANT_IDS[2]),
    )

    assert len(valid_three.members) == 3

    with pytest.raises(ValidationError, match="member_id"):
        comparison_set(
            explicit_member("member-a", APPROVED_VARIANT_IDS[0]),
            explicit_member("member-a", APPROVED_VARIANT_IDS[1]),
        )
    with pytest.raises(ValidationError, match="scopes"):
        comparison_set(
            explicit_member("member-a", APPROVED_VARIANT_IDS[0]),
            explicit_member("member-b", APPROVED_VARIANT_IDS[0]),
        )


def test_member_identity_requires_concrete_variant_and_matching_store() -> None:
    with pytest.raises(ValidationError, match="variant_id"):
        ComparisonSetMember(
            member_id="member-product-only",
            scope=ObjectScope(
                store_id=STORE_ID,
                product_id=APPROVED_VARIANT_MAPPING[APPROVED_VARIANT_IDS[0]],
            ),
            provenance=MemberProvenance(
                source_kind=MemberSourceKind.EXPLICIT,
                original_reference="DJI Mini",
                resolver_outcome="product_only_reference",
            ),
            resolution_reason="product-only is not a concrete comparison member",
            catalog_revision="s04-planning-baseline-5af0296",
            display_name="Product only",
        )

    foreign_member = explicit_member("member-foreign", APPROVED_VARIANT_IDS[1])
    foreign_scope = ObjectScope(
        store_id="foreign-store",
        product_id=foreign_member.scope.product_id,
        variant_id=foreign_member.scope.variant_id,
    )
    foreign_member = foreign_member.model_copy(update={"scope": foreign_scope})

    with pytest.raises(ValidationError, match="store_id"):
        comparison_set(
            explicit_member("member-a", APPROVED_VARIANT_IDS[0]), foreign_member
        )


def test_page_context_is_not_a_valid_comparison_member_provenance() -> None:
    schema = MemberSourceKind

    assert "PAGE_CONTEXT" not in {item.value for item in schema}
    with pytest.raises(ValidationError):
        MemberProvenance(
            source_kind="PAGE_CONTEXT",
            original_reference="page object",
            resolver_outcome="implicit_page_fill",
        )


def test_comparison_contract_is_internal_and_does_not_expand_public_request() -> None:
    schema_json = json.dumps(TurnRequest.model_json_schema())

    assert "ComparisonSet" not in schema_json
    assert "comparison_members" not in schema_json
    assert "context_revision" not in schema_json


def test_non_ready_comparison_set_carries_explicit_reason() -> None:
    comparison = ComparisonSet(
        correlation_id="cmp-s04-t01-clarify",
        store_id=STORE_ID,
        members=(
            explicit_member("member-a", APPROVED_VARIANT_IDS[0]),
            explicit_member("member-b", APPROVED_VARIANT_IDS[1]),
        ),
        scope_status=ComparisonScopeStatus.NEEDS_CLARIFICATION,
        clarification_reason="member provenance unavailable",
    )

    assert comparison.scope_status is ComparisonScopeStatus.NEEDS_CLARIFICATION
    with pytest.raises(ValidationError, match="requires clarification"):
        ComparisonSet(
            correlation_id="cmp-s04-t01-invalid",
            store_id=STORE_ID,
            members=comparison.members,
            scope_status=ComparisonScopeStatus.FALLBACK,
        )
