"""S04-T05 internal comparison answer and fail-closed walking skeleton."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from backend.catalog.fixture import CatalogFixtureSnapshot
from backend.common import (
    SCHEMA_VERSION,
    AttributeStatus,
    ObjectScope,
)
from backend.common.contracts import WireModel
from backend.conversation import (
    ComparisonFallbackReason,
    ComparisonScopeStatus,
    ComparisonSet,
    ComparisonSetMember,
    ComparisonSetResolver,
    HandoffRoute,
    MemberSourceKind,
    TypedHandoff,
)
from backend.evidence import (
    ComparisonDegradationReason,
    ComparisonFact,
    ComparisonFactSet,
    ComparisonFactState,
    ComparisonFreshnessVerdict,
    build_dynamic_comparison_facts,
    build_static_comparison_facts,
)
from backend.shopify.port import ShopifyReadPort

type SchemaVersion = Literal["1.0"]
type ComparisonState = AttributeStatus | ComparisonFactState
type SourceClass = Literal["CATALOG", "SHOPIFY_COMMERCE"]

_DEFAULT_STATIC_FIELDS = ("battery_count", "takeoff_weight", "obstacle_sensing")
_DEFAULT_DYNAMIC_FIELDS = ("price", "inventory", "availability")


class ComparisonAnswerOutcome(StrEnum):
    """Outcome of the internal comparison flow."""

    ANSWER = "ANSWER"
    DEGRADED = "DEGRADED"
    FALLBACK = "FALLBACK"


class ComparisonFallbackCode(StrEnum):
    """Actionable, internal fallback reasons for the comparison flow."""

    HANDOFF_NOT_COMPARISON = "HANDOFF_NOT_COMPARISON"
    MEMBER_COUNT_OUT_OF_RANGE = "MEMBER_COUNT_OUT_OF_RANGE"
    MEMBER_DUPLICATE = "MEMBER_DUPLICATE"
    MEMBER_UNRESOLVED = "MEMBER_UNRESOLVED"
    PRODUCT_ONLY_REFERENCE = "PRODUCT_ONLY_REFERENCE"
    CROSS_STORE = "CROSS_STORE"
    CROSS_PRODUCT_DEFERRED = "CROSS_PRODUCT_DEFERRED"
    OWNERSHIP_MISMATCH = "OWNERSHIP_MISMATCH"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    DYNAMIC_FACT_UNAVAILABLE = "DYNAMIC_FACT_UNAVAILABLE"
    INTERNAL_CONSISTENCY = "INTERNAL_CONSISTENCY"


class ComparisonTraceEventType(StrEnum):
    """Replayable stages in the internal comparison correlation chain."""

    HANDOFF_RECEIVED = "HANDOFF_RECEIVED"
    MEMBER_RESOLVED = "MEMBER_RESOLVED"
    STATIC_FACTS_BOUND = "STATIC_FACTS_BOUND"
    DYNAMIC_FACTS_BOUND = "DYNAMIC_FACTS_BOUND"
    ANSWER_PRODUCED = "ANSWER_PRODUCED"
    FALLBACK_PRODUCED = "FALLBACK_PRODUCED"


class ComparisonTraceResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    FALLBACK = "FALLBACK"


class ComparisonTraceEvent(WireModel):
    """Summary-only internal trace event; values remain member scoped."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    correlation_id: str = Field(min_length=1)
    event_type: ComparisonTraceEventType
    result: ComparisonTraceResult
    occurred_at: AwareDatetime
    member_id: str | None = None
    scope: ObjectScope | None = None
    provenance: MemberSourceKind | None = None
    fact_ids: tuple[str, ...] = ()
    fact_states: tuple[ComparisonState, ...] = ()
    source_classes: tuple[SourceClass, ...] = ()
    freshness: tuple[ComparisonFreshnessVerdict, ...] = ()
    degradation_reasons: tuple[ComparisonDegradationReason, ...] = ()
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_event_identity(self) -> ComparisonTraceEvent:
        if not self.correlation_id.strip():
            raise ValueError("comparison trace correlation_id must be non-empty")
        if self.member_id is None and (
            self.scope is not None or self.provenance is not None
        ):
            raise ValueError("member-scoped trace fields require member_id")
        if len(set(self.fact_ids)) != len(self.fact_ids):
            raise ValueError("comparison trace fact_ids must be unique")
        return self


class ComparisonTrace(WireModel):
    """Immutable trace reference for one comparison turn."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    correlation_id: str = Field(min_length=1)
    events: tuple[ComparisonTraceEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_event_correlations(self) -> ComparisonTrace:
        if not self.correlation_id.strip():
            raise ValueError("comparison trace correlation_id must be non-empty")
        if any(event.correlation_id != self.correlation_id for event in self.events):
            raise ValueError("all comparison trace events must share correlation_id")
        return self


class ComparisonFactCell(WireModel):
    """One member's value in a comparison row."""

    member_id: str = Field(min_length=1)
    fact_id: str = Field(min_length=1)
    field_key: str = Field(min_length=1)
    state: ComparisonState
    value: JsonValue | None = None
    unit: str | None = None
    evidence_id: str = Field(min_length=1)
    scope: ObjectScope
    source_class: SourceClass
    freshness: ComparisonFreshnessVerdict | None = None

    @model_validator(mode="after")
    def validate_cell_identity(self) -> ComparisonFactCell:
        if self.scope.variant_id is None:
            raise ValueError("comparison cells require a concrete Variant scope")
        state_value = self.state.value
        if state_value == AttributeStatus.KNOWN.value:
            if self.value is None:
                raise ValueError("KNOWN comparison cells require a value")
        elif self.value is not None:
            raise ValueError("non-KNOWN comparison cells must omit value")
        if self.source_class == "CATALOG" and self.freshness is not None:
            raise ValueError("catalog comparison cells cannot carry freshness")
        if self.source_class == "SHOPIFY_COMMERCE" and self.freshness is None:
            raise ValueError("commerce comparison cells require freshness")
        return self


class ComparisonDifferenceMember(WireModel):
    """A known member value participating in one difference."""

    member_id: str = Field(min_length=1)
    fact_id: str = Field(min_length=1)
    value: JsonValue


class ComparisonDifference(WireModel):
    """A difference formed only when every participating cell is known."""

    field_key: str = Field(min_length=1)
    members: tuple[ComparisonDifferenceMember, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_difference_members(self) -> ComparisonDifference:
        member_ids = [member.member_id for member in self.members]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("comparison difference members must be unique")
        first_value = self.members[0].value
        if all(member.value == first_value for member in self.members[1:]):
            raise ValueError("comparison difference requires distinct values")
        return self


class ComparisonRow(WireModel):
    """One field row retaining the original member ordering."""

    field_key: str = Field(min_length=1)
    cells: tuple[ComparisonFactCell, ...] = Field(min_length=2)
    difference: ComparisonDifference | None = None

    @model_validator(mode="after")
    def validate_row_cells(self) -> ComparisonRow:
        if any(cell.field_key != self.field_key for cell in self.cells):
            raise ValueError("comparison row cells must use the row field_key")
        member_ids = [cell.member_id for cell in self.cells]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("comparison row cells must use unique members")
        if self.difference is not None and self.difference.field_key != self.field_key:
            raise ValueError("comparison difference must use the row field_key")
        return self


class ComparisonDisclosure(WireModel):
    """Per-member identity and provenance disclosed with an answer."""

    correlation_id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    members: tuple[ComparisonSetMember, ...] = Field(min_length=2, max_length=4)
    catalog_revision: str = Field(min_length=1)
    dynamic_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_member_disclosure(self) -> ComparisonDisclosure:
        if not self.correlation_id.strip():
            raise ValueError("comparison disclosure correlation_id must be non-empty")
        member_ids = [member.member_id for member in self.members]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("comparison disclosure member IDs must be unique")
        for member in self.members:
            if member.scope.store_id != self.store_id:
                raise ValueError("comparison disclosure crossed store scope")
            if member.scope.product_id != self.product_id:
                raise ValueError("comparison disclosure crossed Product scope")
        return self


class ComparisonFallback(WireModel):
    """Safe next action when a comparison cannot be fully answered."""

    reason: ComparisonFallbackCode
    message: str = Field(min_length=1)
    retryable: bool = False
    next_actions: tuple[str, ...] = Field(min_length=1)
    candidates: tuple[ObjectScope, ...] = ()


class ComparisonAnswer(WireModel):
    """Internal S04 answer, degraded answer, or typed fallback."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    correlation_id: str = Field(min_length=1)
    outcome: ComparisonAnswerOutcome
    comparison_set: ComparisonSet | None = None
    static_facts: ComparisonFactSet
    dynamic_facts: ComparisonFactSet
    rows: tuple[ComparisonRow, ...] = ()
    differences: tuple[ComparisonDifference, ...] = ()
    disclosure: ComparisonDisclosure | None = None
    fallback: ComparisonFallback | None = None
    trace: ComparisonTrace

    @property
    def status(self) -> ComparisonAnswerOutcome:
        """Compatibility spelling for callers that use ``status``."""

        return self.outcome

    @model_validator(mode="after")
    def validate_answer_shape(self) -> ComparisonAnswer:
        if not self.correlation_id.strip():
            raise ValueError("comparison answer correlation_id must be non-empty")
        if self.static_facts.correlation_id != self.correlation_id:
            raise ValueError("static facts must share answer correlation_id")
        if self.dynamic_facts.correlation_id != self.correlation_id:
            raise ValueError("dynamic facts must share answer correlation_id")
        if self.trace.correlation_id != self.correlation_id:
            raise ValueError("trace must share answer correlation_id")

        if self.outcome is ComparisonAnswerOutcome.FALLBACK:
            if self.comparison_set is not None or self.disclosure is not None:
                raise ValueError("fallback answers cannot disclose a ready set")
            if self.rows or self.differences or self.fallback is None:
                raise ValueError("fallback answers require fallback and no rows")
        else:
            if self.comparison_set is None or self.disclosure is None:
                raise ValueError("answer outcomes require set and disclosure")
            if (
                self.fallback is not None
                and self.outcome is ComparisonAnswerOutcome.ANSWER
            ):
                raise ValueError("ANSWER outcomes cannot carry fallback")
            if not self.rows:
                raise ValueError("answer outcomes require comparison rows")
            if self.disclosure.correlation_id != self.correlation_id:
                raise ValueError("disclosure must share answer correlation_id")
            if self.disclosure.members != self.comparison_set.members:
                raise ValueError("disclosure must preserve the resolved member set")
            members_by_id = {
                member.member_id: member for member in self.comparison_set.members
            }
            facts_by_id = {
                fact.comparison_fact_id: fact
                for fact in (*self.static_facts.facts, *self.dynamic_facts.facts)
            }
            for fact in facts_by_id.values():
                member = members_by_id.get(fact.member_id)
                if member is None or fact.binding.scope != member.scope:
                    raise ValueError(
                        "fact evidence scope must match its comparison member"
                    )
            for row in self.rows:
                if {cell.member_id for cell in row.cells} != set(members_by_id):
                    raise ValueError(
                        "comparison row must include every resolved member"
                    )
                for cell in row.cells:
                    member = members_by_id.get(cell.member_id)
                    fact = facts_by_id.get(cell.fact_id)
                    if (
                        member is None
                        or fact is None
                        or fact.member_id != cell.member_id
                        or fact.field_key != row.field_key
                        or fact.binding.evidence_id != cell.evidence_id
                        or fact.binding.scope != cell.scope
                    ):
                        raise ValueError(
                            "comparison row cell is not bound to its member fact"
                        )
        return self


class ComparisonApplicationService:
    """Compose typed handoff, identity resolution, facts, and internal output."""

    def __init__(
        self,
        *,
        snapshot: CatalogFixtureSnapshot,
        shopify: ShopifyReadPort,
        catalog_revision: str,
        clock: Callable[[], datetime],
        correlation_id_factory: Callable[[], str] | None = None,
        freshness_window: timedelta = timedelta(minutes=5),
        static_field_keys: Iterable[str] = _DEFAULT_STATIC_FIELDS,
        dynamic_field_keys: Iterable[str] = _DEFAULT_DYNAMIC_FIELDS,
    ) -> None:
        if not catalog_revision.strip():
            raise ValueError("catalog_revision must be non-empty")
        if freshness_window <= timedelta(0):
            raise ValueError("freshness_window must be positive")
        self._snapshot = snapshot
        self._shopify = shopify
        self._catalog_revision = catalog_revision
        self._clock = clock
        self._correlation_id_factory = correlation_id_factory or (
            lambda: "comparison-s04"
        )
        self._freshness_window = freshness_window
        self._static_field_keys = _validate_fields(static_field_keys)
        self._dynamic_field_keys = _validate_fields(dynamic_field_keys)

    def answer(
        self,
        handoff: TypedHandoff,
        *,
        correlation_id: str | None = None,
        confirmed_context_revision: int = 0,
    ) -> ComparisonAnswer:
        """Return an internal comparison answer without changing conversation state."""
        trace_id = correlation_id or self._correlation_id_factory()
        _require_correlation_id(trace_id)
        now = self._clock()
        _require_aware_datetime(now)
        events: list[ComparisonTraceEvent] = []
        _append_event(
            events,
            correlation_id=trace_id,
            event_type=ComparisonTraceEventType.HANDOFF_RECEIVED,
            result=(
                ComparisonTraceResult.ACCEPTED
                if handoff.route is HandoffRoute.COMPARISON
                else ComparisonTraceResult.FALLBACK
            ),
            occurred_at=now,
            detail=f"route={handoff.route.value}",
        )

        empty_static = _empty_fact_set(trace_id)
        empty_dynamic = _empty_fact_set(trace_id)
        if handoff.route is not HandoffRoute.COMPARISON:
            return self._fallback(
                correlation_id=trace_id,
                events=events,
                occurred_at=now,
                reason=ComparisonFallbackCode.HANDOFF_NOT_COMPARISON,
                candidates=(),
                static_facts=empty_static,
                dynamic_facts=empty_dynamic,
            )

        resolution = ComparisonSetResolver(
            snapshot=self._snapshot,
            catalog_revision=self._catalog_revision,
        ).materialize(
            target=handoff.target,
            correlation_id=trace_id,
            confirmed_context_revision=confirmed_context_revision,
        )
        if resolution.status is not ComparisonScopeStatus.READY:
            reason = _fallback_code(resolution.fallback_reason)
            _append_event(
                events,
                correlation_id=trace_id,
                event_type=ComparisonTraceEventType.FALLBACK_PRODUCED,
                result=ComparisonTraceResult.FALLBACK,
                occurred_at=now,
                detail=f"resolution={reason.value}",
            )
            return self._fallback(
                correlation_id=trace_id,
                events=events,
                occurred_at=now,
                reason=reason,
                candidates=resolution.candidates,
                static_facts=empty_static,
                dynamic_facts=empty_dynamic,
            )

        comparison_set = resolution.comparison_set
        if comparison_set is None:
            return self._fallback(
                correlation_id=trace_id,
                events=events,
                occurred_at=now,
                reason=ComparisonFallbackCode.INTERNAL_CONSISTENCY,
                candidates=(),
                static_facts=empty_static,
                dynamic_facts=empty_dynamic,
            )

        for member in comparison_set.members:
            _append_event(
                events,
                correlation_id=trace_id,
                event_type=ComparisonTraceEventType.MEMBER_RESOLVED,
                result=ComparisonTraceResult.SUCCESS,
                occurred_at=now,
                member_id=member.member_id,
                scope=member.scope,
                provenance=member.provenance.source_kind,
                detail="concrete Variant identity validated",
            )

        try:
            static_facts = build_static_comparison_facts(
                comparison_set=comparison_set,
                snapshot=self._snapshot,
                field_keys=self._static_field_keys,
            )
        except Exception:
            return self._fallback(
                correlation_id=trace_id,
                events=events,
                occurred_at=now,
                reason=ComparisonFallbackCode.INTERNAL_CONSISTENCY,
                candidates=tuple(member.scope for member in comparison_set.members),
                static_facts=empty_static,
                dynamic_facts=empty_dynamic,
            )
        _append_fact_events(
            events,
            correlation_id=trace_id,
            event_type=ComparisonTraceEventType.STATIC_FACTS_BOUND,
            result=ComparisonTraceResult.SUCCESS,
            occurred_at=now,
            facts=static_facts,
            members=comparison_set.members,
        )
        if _missing_facts(static_facts, comparison_set, self._static_field_keys):
            return self._fallback(
                correlation_id=trace_id,
                events=events,
                occurred_at=now,
                reason=ComparisonFallbackCode.EVIDENCE_MISSING,
                candidates=tuple(member.scope for member in comparison_set.members),
                static_facts=static_facts,
                dynamic_facts=empty_dynamic,
            )

        try:
            dynamic_facts = build_dynamic_comparison_facts(
                comparison_set=comparison_set,
                shopify=self._shopify,
                now=now,
                freshness_window=self._freshness_window,
                field_keys=self._dynamic_field_keys,
            )
        except Exception:
            _append_event(
                events,
                correlation_id=trace_id,
                event_type=ComparisonTraceEventType.DYNAMIC_FACTS_BOUND,
                result=ComparisonTraceResult.UNAVAILABLE,
                occurred_at=now,
                detail="dynamic read could not be materialized",
            )
            return self._fallback(
                correlation_id=trace_id,
                events=events,
                occurred_at=now,
                reason=ComparisonFallbackCode.DYNAMIC_FACT_UNAVAILABLE,
                candidates=tuple(member.scope for member in comparison_set.members),
                static_facts=static_facts,
                dynamic_facts=empty_dynamic,
            )
        _append_fact_events(
            events,
            correlation_id=trace_id,
            event_type=ComparisonTraceEventType.DYNAMIC_FACTS_BOUND,
            result=(
                ComparisonTraceResult.PARTIAL
                if _has_unavailable(dynamic_facts)
                else ComparisonTraceResult.SUCCESS
            ),
            occurred_at=now,
            facts=dynamic_facts,
            members=comparison_set.members,
        )
        if _missing_facts(dynamic_facts, comparison_set, self._dynamic_field_keys):
            return self._fallback(
                correlation_id=trace_id,
                events=events,
                occurred_at=now,
                reason=ComparisonFallbackCode.DYNAMIC_FACT_UNAVAILABLE,
                candidates=tuple(member.scope for member in comparison_set.members),
                static_facts=static_facts,
                dynamic_facts=dynamic_facts,
            )

        rows, differences = _build_rows(
            comparison_set=comparison_set,
            static_facts=static_facts,
            dynamic_facts=dynamic_facts,
            static_field_keys=self._static_field_keys,
            dynamic_field_keys=self._dynamic_field_keys,
        )
        disclosure = ComparisonDisclosure(
            correlation_id=trace_id,
            store_id=comparison_set.store_id,
            product_id=comparison_set.members[0].scope.product_id,
            members=comparison_set.members,
            catalog_revision=self._catalog_revision,
            dynamic_fields=self._dynamic_field_keys,
        )
        degraded = _has_unavailable(dynamic_facts)
        fallback = (
            _fallback_detail(
                ComparisonFallbackCode.DYNAMIC_FACT_UNAVAILABLE,
                candidates=tuple(member.scope for member in comparison_set.members),
            )
            if degraded
            else None
        )
        _append_event(
            events,
            correlation_id=trace_id,
            event_type=ComparisonTraceEventType.ANSWER_PRODUCED,
            result=(
                ComparisonTraceResult.PARTIAL
                if degraded
                else ComparisonTraceResult.SUCCESS
            ),
            occurred_at=now,
            detail="member-scoped comparison rows assembled",
        )
        return ComparisonAnswer(
            correlation_id=trace_id,
            outcome=(
                ComparisonAnswerOutcome.DEGRADED
                if degraded
                else ComparisonAnswerOutcome.ANSWER
            ),
            comparison_set=comparison_set,
            static_facts=static_facts,
            dynamic_facts=dynamic_facts,
            rows=rows,
            differences=differences,
            disclosure=disclosure,
            fallback=fallback,
            trace=ComparisonTrace(correlation_id=trace_id, events=tuple(events)),
        )

    def _fallback(
        self,
        *,
        correlation_id: str,
        events: list[ComparisonTraceEvent],
        occurred_at: datetime,
        reason: ComparisonFallbackCode,
        candidates: tuple[ObjectScope, ...],
        static_facts: ComparisonFactSet,
        dynamic_facts: ComparisonFactSet,
    ) -> ComparisonAnswer:
        detail = _fallback_detail(reason, candidates=candidates)
        _append_event(
            events,
            correlation_id=correlation_id,
            event_type=ComparisonTraceEventType.FALLBACK_PRODUCED,
            result=ComparisonTraceResult.FALLBACK,
            occurred_at=occurred_at,
            detail=f"fallback={reason.value}",
        )
        return ComparisonAnswer(
            correlation_id=correlation_id,
            outcome=ComparisonAnswerOutcome.FALLBACK,
            static_facts=static_facts,
            dynamic_facts=dynamic_facts,
            fallback=detail,
            trace=ComparisonTrace(
                correlation_id=correlation_id,
                events=tuple(events),
            ),
        )


def _validate_fields(field_keys: Iterable[str]) -> tuple[str, ...]:
    fields = tuple(field_keys)
    if not fields or any(
        not isinstance(field, str) or not field.strip() for field in fields
    ):
        raise ValueError("comparison field keys must be non-empty")
    if len(set(fields)) != len(fields):
        raise ValueError("comparison field keys must be unique")
    return fields


def _require_correlation_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("comparison correlation_id must be non-empty")


def _require_aware_datetime(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("comparison clock must return a timezone-aware datetime")


def _empty_fact_set(correlation_id: str) -> ComparisonFactSet:
    return ComparisonFactSet(correlation_id=correlation_id, facts=())


def _fallback_code(reason: ComparisonFallbackReason | None) -> ComparisonFallbackCode:
    if reason is None:
        return ComparisonFallbackCode.INTERNAL_CONSISTENCY
    try:
        return ComparisonFallbackCode(reason.value)
    except ValueError:
        return ComparisonFallbackCode.INTERNAL_CONSISTENCY


def _fallback_detail(
    reason: ComparisonFallbackCode,
    *,
    candidates: tuple[ObjectScope, ...],
) -> ComparisonFallback:
    messages = {
        ComparisonFallbackCode.HANDOFF_NOT_COMPARISON: (
            "当前 typed handoff 不是比较请求。",
            False,
            ("重新发起同一 Product 下两个至四个具体 Variant 的比较",),
        ),
        ComparisonFallbackCode.PRODUCT_ONLY_REFERENCE: (
            "比较成员仍缺少具体 Variant，暂不猜测默认选项。",
            False,
            ("补充每个 Variant 的明确选择",),
        ),
        ComparisonFallbackCode.CROSS_PRODUCT_DEFERRED: (
            "当前版本只支持同一 Product 的 Variant 比较。",
            False,
            ("改为选择同一 Product 下的两个至四个 Variant",),
        ),
        ComparisonFallbackCode.CROSS_STORE: (
            "比较成员必须属于当前商店。",
            False,
            ("确认所有 Variant 来自同一商店",),
        ),
        ComparisonFallbackCode.OWNERSHIP_MISMATCH: (
            "Variant 与 Product 的归属不一致，未生成比较。",
            False,
            ("重新提供正确的 Product / Variant 配对",),
        ),
        ComparisonFallbackCode.MEMBER_UNRESOLVED: (
            "至少一个比较成员无法解析。",
            False,
            ("补充可解析的具体 Variant",),
        ),
        ComparisonFallbackCode.MEMBER_COUNT_OUT_OF_RANGE: (
            "比较需要两个至四个具体 Variant。",
            False,
            ("调整比较成员数量至两个至四个",),
        ),
        ComparisonFallbackCode.MEMBER_DUPLICATE: (
            "比较成员不能重复。",
            False,
            ("移除重复 Variant 后重试",),
        ),
        ComparisonFallbackCode.EVIDENCE_MISSING: (
            "部分比较事实缺少可验证的成员证据。",
            False,
            ("补充目录事实后重试比较",),
        ),
        ComparisonFallbackCode.DYNAMIC_FACT_UNAVAILABLE: (
            "当前价格、库存或 availability 读取不可用，未使用旧值替代。",
            True,
            ("稍后重试动态读取", "仅查看仍有证据的静态字段"),
        ),
        ComparisonFallbackCode.INTERNAL_CONSISTENCY: (
            "暂时无法可靠生成比较，请停止展示该结论。",
            False,
            ("停止展示该结论", "检查成员和目录证据后重试"),
        ),
    }
    message, retryable, next_actions = messages[reason]
    return ComparisonFallback(
        reason=reason,
        message=message,
        retryable=retryable,
        next_actions=next_actions,
        candidates=candidates,
    )


def _append_event(
    events: list[ComparisonTraceEvent],
    *,
    correlation_id: str,
    event_type: ComparisonTraceEventType,
    result: ComparisonTraceResult,
    occurred_at: datetime,
    detail: str,
    member_id: str | None = None,
    scope: ObjectScope | None = None,
    provenance: MemberSourceKind | None = None,
    fact_ids: tuple[str, ...] = (),
    fact_states: tuple[ComparisonState, ...] = (),
    source_classes: tuple[SourceClass, ...] = (),
    freshness: tuple[ComparisonFreshnessVerdict, ...] = (),
    degradation_reasons: tuple[ComparisonDegradationReason, ...] = (),
) -> None:
    events.append(
        ComparisonTraceEvent(
            correlation_id=correlation_id,
            event_type=event_type,
            result=result,
            occurred_at=occurred_at,
            member_id=member_id,
            scope=scope,
            provenance=provenance,
            fact_ids=fact_ids,
            fact_states=fact_states,
            source_classes=source_classes,
            freshness=freshness,
            degradation_reasons=degradation_reasons,
            detail=detail,
        )
    )


def _append_fact_events(
    events: list[ComparisonTraceEvent],
    *,
    correlation_id: str,
    event_type: ComparisonTraceEventType,
    result: ComparisonTraceResult,
    occurred_at: datetime,
    facts: ComparisonFactSet,
    members: tuple[ComparisonSetMember, ...],
) -> None:
    by_member: dict[str, list[ComparisonFact]] = {
        member.member_id: [] for member in members
    }
    for fact in facts.facts:
        by_member.setdefault(fact.member_id, []).append(fact)
    for member in members:
        member_facts = by_member.get(member.member_id, [])
        _append_event(
            events,
            correlation_id=correlation_id,
            event_type=event_type,
            result=result,
            occurred_at=occurred_at,
            member_id=member.member_id,
            scope=member.scope,
            fact_ids=tuple(fact.comparison_fact_id for fact in member_facts),
            fact_states=tuple(fact.state for fact in member_facts),
            source_classes=tuple(
                dict.fromkeys(fact.source_class for fact in member_facts)
            ),
            freshness=tuple(
                dict.fromkeys(
                    fact.freshness.verdict
                    for fact in member_facts
                    if fact.freshness is not None
                )
            ),
            degradation_reasons=tuple(
                dict.fromkeys(
                    fact.degradation_reason
                    for fact in member_facts
                    if fact.degradation_reason is not None
                )
            ),
            detail=f"{event_type.value.lower()} member facts",
        )


def _missing_facts(
    facts: ComparisonFactSet,
    comparison_set: ComparisonSet,
    field_keys: tuple[str, ...],
) -> bool:
    actual = {(fact.member_id, fact.field_key) for fact in facts.facts}
    expected = {
        (member.member_id, field_key)
        for member in comparison_set.members
        for field_key in field_keys
    }
    return not expected.issubset(actual)


def _has_unavailable(facts: ComparisonFactSet) -> bool:
    return any(
        fact.state.value == ComparisonFactState.UNAVAILABLE.value
        for fact in facts.facts
    )


def _build_rows(
    *,
    comparison_set: ComparisonSet,
    static_facts: ComparisonFactSet,
    dynamic_facts: ComparisonFactSet,
    static_field_keys: tuple[str, ...],
    dynamic_field_keys: tuple[str, ...],
) -> tuple[tuple[ComparisonRow, ...], tuple[ComparisonDifference, ...]]:
    fact_by_key = {
        (fact.member_id, fact.field_key): fact
        for fact in (*static_facts.facts, *dynamic_facts.facts)
    }
    rows: list[ComparisonRow] = []
    differences: list[ComparisonDifference] = []
    field_keys = (*static_field_keys, *dynamic_field_keys)
    for field_key in field_keys:
        cells = tuple(
            _cell(fact_by_key[(member.member_id, field_key)])
            for member in comparison_set.members
        )
        difference = _difference(field_key, cells)
        row = ComparisonRow(
            field_key=field_key,
            cells=cells,
            difference=difference,
        )
        rows.append(row)
        if difference is not None:
            differences.append(difference)
    return tuple(rows), tuple(differences)


def _cell(fact: ComparisonFact) -> ComparisonFactCell:
    return ComparisonFactCell(
        member_id=fact.member_id,
        fact_id=fact.comparison_fact_id,
        field_key=fact.field_key,
        state=fact.state,
        value=fact.fact.value,
        unit=fact.fact.unit,
        evidence_id=fact.binding.evidence_id,
        scope=fact.binding.scope,
        source_class=fact.source_class,
        freshness=(fact.freshness.verdict if fact.freshness is not None else None),
    )


def _difference(
    field_key: str,
    cells: tuple[ComparisonFactCell, ...],
) -> ComparisonDifference | None:
    if not cells or any(
        cell.state.value != AttributeStatus.KNOWN.value for cell in cells
    ):
        return None
    first = cells[0].value
    if all(cell.value == first for cell in cells[1:]):
        return None
    return ComparisonDifference(
        field_key=field_key,
        members=tuple(
            ComparisonDifferenceMember(
                member_id=cell.member_id,
                fact_id=cell.fact_id,
                value=cell.value,
            )
            for cell in cells
        ),
    )


# Short aliases make the internal boundary discoverable without introducing a
# second implementation name or changing the public AnswerEnvelope schema.
ComparisonFlowService = ComparisonApplicationService
ComparisonApplication = ComparisonApplicationService
ComparisonOutcome = ComparisonAnswerOutcome
