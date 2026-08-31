"""Deterministic single-turn constraints for Slice 2 recommendation work."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, JsonValue, StrictFloat, model_validator

from backend.common import SCHEMA_VERSION, TurnRequest
from backend.common.contracts import WireModel

type SchemaVersion = Literal["1.0"]


class ConstraintOperation(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    NO_CHANGE = "NO_CHANGE"


class ConstraintField(StrEnum):
    PRICE = "price"
    TAKEOFF_WEIGHT = "takeoff_weight"
    BATTERY_COUNT = "battery_count"
    USE_CASE = "use_case"
    CAMERA_RESOLUTION = "camera_resolution"
    OBSTACLE_SENSING = "obstacle_sensing"


class ConstraintOperator(StrEnum):
    LTE = "LTE"
    GTE = "GTE"
    EQ = "EQ"
    PRESENT = "PRESENT"


class ConstraintHardness(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"


class ConstraintProvenance(StrEnum):
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"
    UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"


class NormalizedConstraintStatus(StrEnum):
    ACTIVE = "ACTIVE"


_ALLOWED_UNITS: dict[ConstraintField, set[str | None]] = {
    ConstraintField.PRICE: {"CNY", "yuan"},
    ConstraintField.TAKEOFF_WEIGHT: {"g", "kg"},
    ConstraintField.BATTERY_COUNT: {"battery"},
    ConstraintField.USE_CASE: {None},
    ConstraintField.CAMERA_RESOLUTION: {None},
    ConstraintField.OBSTACLE_SENSING: {None},
}

_NORMAL_UNITS: dict[ConstraintField, str | None] = {
    ConstraintField.PRICE: "CNY",
    ConstraintField.TAKEOFF_WEIGHT: "g",
    ConstraintField.BATTERY_COUNT: "battery",
    ConstraintField.USE_CASE: None,
    ConstraintField.CAMERA_RESOLUTION: None,
    ConstraintField.OBSTACLE_SENSING: None,
}

_NUMERIC_FIELDS = {
    ConstraintField.PRICE,
    ConstraintField.TAKEOFF_WEIGHT,
    ConstraintField.BATTERY_COUNT,
}

_FIELD_OPERATORS: dict[ConstraintField, set[ConstraintOperator]] = {
    ConstraintField.PRICE: {ConstraintOperator.LTE},
    ConstraintField.TAKEOFF_WEIGHT: {ConstraintOperator.LTE},
    ConstraintField.BATTERY_COUNT: {ConstraintOperator.GTE},
    ConstraintField.USE_CASE: {ConstraintOperator.EQ},
    ConstraintField.CAMERA_RESOLUTION: {ConstraintOperator.EQ},
    ConstraintField.OBSTACLE_SENSING: {ConstraintOperator.PRESENT},
}


class ConstraintPatch(WireModel):
    """One deterministic single-turn constraint patch."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    source_turn_id: str
    operation: ConstraintOperation
    field: ConstraintField | None = None
    operator: ConstraintOperator | None = None
    value: JsonValue | None = None
    unit: str | None = None
    hardness: ConstraintHardness | None = None
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    provenance: ConstraintProvenance
    reason: str

    @model_validator(mode="after")
    def validate_patch_shape(self) -> ConstraintPatch:
        supplied = self.model_fields_set
        semantic_fields = {"field", "operator", "value", "unit", "hardness"}
        if self.operation is ConstraintOperation.NO_CHANGE:
            if semantic_fields & supplied:
                raise ValueError("NO_CHANGE must omit constraint semantics")
            if self.provenance is not ConstraintProvenance.UNSUPPORTED_INPUT:
                raise ValueError("NO_CHANGE requires UNSUPPORTED_INPUT provenance")
            return self

        missing = {"field", "operator", "value", "hardness"} - supplied
        if missing:
            raise ValueError("ADD/UPDATE require field, operator, value, and hardness")
        if self.field is None or self.operator is None or self.hardness is None:
            raise ValueError("ADD/UPDATE constraint semantics cannot be null")
        if self.provenance is ConstraintProvenance.UNSUPPORTED_INPUT:
            raise ValueError("ADD/UPDATE cannot use UNSUPPORTED_INPUT provenance")
        if self.unit not in _ALLOWED_UNITS[self.field]:
            raise ValueError(f"{self.field.value} does not accept unit {self.unit}")
        if self.operator not in _FIELD_OPERATORS[self.field]:
            raise ValueError(f"{self.operator.value} is not valid for {self.field}")
        if self.field in _NUMERIC_FIELDS and (
            isinstance(self.value, bool) or not isinstance(self.value, int | float)
        ):
            raise ValueError(f"{self.field.value} requires a numeric value")
        if self.field not in _NUMERIC_FIELDS and not isinstance(self.value, str | bool):
            raise ValueError(f"{self.field.value} requires a string or boolean value")
        if (
            self.operator is ConstraintOperator.PRESENT
            and self.field in _NUMERIC_FIELDS
        ):
            raise ValueError("PRESENT is only valid for non-numeric feature fields")
        return self


class NormalizedConstraint(WireModel):
    """Comparable constraint consumed by later eligibility/ranking tasks."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    source_turn_id: str
    field: ConstraintField
    operator: ConstraintOperator
    value: JsonValue
    unit: str | None = None
    hardness: ConstraintHardness
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    provenance: ConstraintProvenance
    status: NormalizedConstraintStatus = NormalizedConstraintStatus.ACTIVE

    @model_validator(mode="after")
    def validate_normalized_shape(self) -> NormalizedConstraint:
        if self.unit != _NORMAL_UNITS[self.field]:
            raise ValueError(f"{self.field.value} must normalize to canonical unit")
        if self.field in _NUMERIC_FIELDS and not isinstance(self.value, int | float):
            raise ValueError(f"{self.field.value} requires a numeric normalized value")
        return self


def parse_constraint_patches(request: TurnRequest) -> tuple[ConstraintPatch, ...]:
    """Parse only the approved deterministic Slice 2 vocabulary."""
    text = _normalize_text(request.user_text)
    patches = [
        *_price_constraints(request, text),
        *_weight_constraints(request, text),
        *_battery_constraints(request, text),
        *_use_case_constraints(request, text),
        *_camera_constraints(request, text),
        *_obstacle_constraints(request, text),
    ]
    if patches:
        return tuple(patches)
    return (
        ConstraintPatch(
            source_turn_id=request.conversation.message_id,
            operation=ConstraintOperation.NO_CHANGE,
            confidence=0.0,
            provenance=ConstraintProvenance.UNSUPPORTED_INPUT,
            reason="No approved Slice 2 constraint vocabulary matched this turn.",
        ),
    )


def normalize_constraint_patches(
    patches: tuple[ConstraintPatch, ...],
) -> tuple[NormalizedConstraint, ...]:
    return tuple(
        normalized
        for patch in patches
        if (normalized := normalize_constraint_patch(patch)) is not None
    )


def normalize_constraint_patch(
    patch: ConstraintPatch,
) -> NormalizedConstraint | None:
    if patch.operation is ConstraintOperation.NO_CHANGE:
        return None
    if patch.field is None or patch.operator is None or patch.hardness is None:
        raise ValueError("Cannot normalize an incomplete constraint patch")
    return NormalizedConstraint(
        source_turn_id=patch.source_turn_id,
        field=patch.field,
        operator=patch.operator,
        value=_normalize_value(patch.field, patch.value, patch.unit),
        unit=_NORMAL_UNITS[patch.field],
        hardness=patch.hardness,
        confidence=patch.confidence,
        provenance=patch.provenance,
    )


def _normalize_text(text: str) -> str:
    return text.strip().lower().replace("，", ",").replace("。", ".")


def _price_constraints(request: TurnRequest, text: str) -> tuple[ConstraintPatch, ...]:
    if any(token in text for token in ("usd", "美元", "$", "dollar")) and any(
        token in text for token in ("预算", "价格", "价位", "budget", "price")
    ):
        return ()
    match = re.search(
        r"(?:预算|价格|价位)[^\d]*(\d+(?:\.\d+)?)\s*(?:元|cny|rmb)?", text
    )
    if not match:
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:元|cny|rmb)?(?:以内|以下|以下预算)", text
        )
    if not match:
        return ()
    return (
        _patch(
            request,
            field=ConstraintField.PRICE,
            operator=ConstraintOperator.LTE,
            value=int(float(match.group(1))),
            unit="CNY",
            hardness=ConstraintHardness.HARD,
            reason="Budget ceiling parsed from deterministic price vocabulary.",
        ),
    )


def _weight_constraints(request: TurnRequest, text: str) -> tuple[ConstraintPatch, ...]:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(kg|公斤|千克|g|克|gram|grams)\s*(?:以内|以下|以下的|内|以下重量)?",
        text,
    )
    if not match or not any(
        token in text for token in ("重量", "起飞", "轻", "g", "克", "kg")
    ):
        return ()
    unit = "kg" if match.group(2) in {"kg", "公斤", "千克"} else "g"
    return (
        _patch(
            request,
            field=ConstraintField.TAKEOFF_WEIGHT,
            operator=ConstraintOperator.LTE,
            value=float(match.group(1)) if unit == "kg" else int(float(match.group(1))),
            unit=unit,
            hardness=ConstraintHardness.HARD,
            reason=(
                "Takeoff-weight ceiling parsed from deterministic weight vocabulary."
            ),
        ),
    )


def _battery_constraints(
    request: TurnRequest, text: str
) -> tuple[ConstraintPatch, ...]:
    match = re.search(
        r"(?:至少|不少于|>=?)\s*(\d+)\s*(?:块)?(?:电池|battery|batteries)", text
    )
    if not match:
        match = re.search(r"(\d+)\s*(?:块)?(?:电池|battery|batteries)(?:以上|起)", text)
    if not match:
        return ()
    return (
        _patch(
            request,
            field=ConstraintField.BATTERY_COUNT,
            operator=ConstraintOperator.GTE,
            value=int(match.group(1)),
            unit="battery",
            hardness=ConstraintHardness.HARD,
            reason="Minimum battery count parsed from deterministic bundle vocabulary.",
        ),
    )


def _use_case_constraints(
    request: TurnRequest, text: str
) -> tuple[ConstraintPatch, ...]:
    if any(token in text for token in ("旅行", "旅游", "出门", "travel")):
        value = "travel"
    elif any(token in text for token in ("电影", "影视", "cinema", "拍片")):
        value = "cinema"
    elif any(token in text for token in ("巡检", "测绘", "inspection", "survey")):
        value = "inspection"
    else:
        return ()
    return (
        _patch(
            request,
            field=ConstraintField.USE_CASE,
            operator=ConstraintOperator.EQ,
            value=value,
            unit=None,
            hardness=ConstraintHardness.SOFT,
            reason="Use-case preference parsed as a transparent SOFT signal.",
        ),
    )


def _camera_constraints(request: TurnRequest, text: str) -> tuple[ConstraintPatch, ...]:
    if "5.1k" in text:
        value = "5.1K"
    elif "4k" in text or "4 k" in text:
        value = "4K"
    else:
        return ()
    return (
        _patch(
            request,
            field=ConstraintField.CAMERA_RESOLUTION,
            operator=ConstraintOperator.EQ,
            value=value,
            unit=None,
            hardness=ConstraintHardness.SOFT,
            reason="Camera-resolution preference parsed as a transparent SOFT signal.",
        ),
    )


def _obstacle_constraints(
    request: TurnRequest, text: str
) -> tuple[ConstraintPatch, ...]:
    if not any(token in text for token in ("避障", "obstacle")):
        return ()
    return (
        _patch(
            request,
            field=ConstraintField.OBSTACLE_SENSING,
            operator=ConstraintOperator.PRESENT,
            value=True,
            unit=None,
            hardness=ConstraintHardness.SOFT,
            reason="Obstacle-sensing preference parsed as a transparent SOFT signal.",
        ),
    )


def _patch(
    request: TurnRequest,
    *,
    field: ConstraintField,
    operator: ConstraintOperator,
    value: Any,
    unit: str | None,
    hardness: ConstraintHardness,
    reason: str,
) -> ConstraintPatch:
    return ConstraintPatch(
        source_turn_id=request.conversation.message_id,
        operation=ConstraintOperation.ADD,
        field=field,
        operator=operator,
        value=value,
        unit=unit,
        hardness=hardness,
        confidence=1.0,
        provenance=ConstraintProvenance.DETERMINISTIC_RULE,
        reason=reason,
    )


def _normalize_value(
    field: ConstraintField, value: JsonValue | None, unit: str | None
) -> JsonValue:
    if field is ConstraintField.PRICE:
        if not isinstance(value, int | float):
            raise ValueError("price requires numeric value")
        return int(value)
    if field is ConstraintField.TAKEOFF_WEIGHT:
        if not isinstance(value, int | float):
            raise ValueError("takeoff_weight requires numeric value")
        if unit == "kg":
            return int(round(float(value) * 1000))
        return int(value)
    if field is ConstraintField.BATTERY_COUNT:
        if not isinstance(value, int | float):
            raise ValueError("battery_count requires numeric value")
        return int(value)
    if value is None:
        raise ValueError(f"{field.value} requires a value")
    return value
