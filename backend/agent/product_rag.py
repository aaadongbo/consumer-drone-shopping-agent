"""Bounded two-round Product RAG retrieval loop for Slice 5."""

from collections.abc import Callable
from enum import StrEnum
from time import monotonic
from typing import Protocol

from pydantic import Field, model_validator

from backend.common import ObjectScope
from backend.evidence import (
    EvidenceGateResult,
    RagClaim,
    RagFallbackReason,
    gate_retrieval_evidence,
    reject_for_budget,
)
from backend.rag.manifest import RagModel
from backend.rag.retrieval import RetrievalRequest, RetrievalResult


class ProductRagRetriever(Protocol):
    """The only read capability the bounded loop may call."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...


class RagAction(StrEnum):
    BASELINE_RETRIEVAL = "BASELINE_RETRIEVAL"
    TARGETED_RETRIEVAL = "TARGETED_RETRIEVAL"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"


class RagStopReason(StrEnum):
    EVIDENCE_ACCEPTED = "EVIDENCE_ACCEPTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    DYNAMIC_FACT_REQUIRED = "DYNAMIC_FACT_REQUIRED"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    ACTION_ROUND_LIMIT = "ACTION_ROUND_LIMIT"
    TOOL_CALL_LIMIT = "TOOL_CALL_LIMIT"
    TURN_DEADLINE = "TURN_DEADLINE"
    RETRIEVAL_TOKEN_BUDGET = "RETRIEVAL_TOKEN_BUDGET"


class ActionVerificationResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NOT_RUN = "NOT_RUN"


class ProductRagBudget(RagModel):
    """Fixed provisional limits from the approved Slice 5 plan."""

    max_action_rounds: int = Field(default=2, ge=1, le=2)
    max_tool_calls: int = Field(default=2, ge=1, le=2)
    turn_deadline_ms: int = Field(default=8000, ge=1)
    max_retrieval_tokens: int = Field(default=4000, ge=1)
    max_model_tokens: int = Field(default=1200, ge=1)


class ActionPlan(RagModel):
    """One allowed action with a fixed single-object target."""

    round_number: int = Field(ge=1, le=2)
    action: RagAction
    target_scope: ObjectScope
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_round_action(self) -> "ActionPlan":
        if self.round_number == 1 and self.action is not RagAction.BASELINE_RETRIEVAL:
            raise ValueError("round one must be baseline retrieval")
        if self.round_number == 2 and self.action is RagAction.BASELINE_RETRIEVAL:
            raise ValueError("corrective round cannot repeat baseline action")
        return self


class BudgetConsumption(RagModel):
    action_rounds: int = Field(ge=0, le=2)
    tool_calls: int = Field(ge=0, le=2)
    retrieval_tokens: int = Field(ge=0)
    model_tokens: int = Field(default=0, ge=0)


class ActionObservation(RagModel):
    evidence_count: int = Field(ge=0)
    missing_reason: str | None = None


class ActionRoundTrace(RagModel):
    """Replayable trace for one permitted Product RAG action."""

    action_plan: ActionPlan
    choice_reason: str = Field(min_length=1)
    observation: ActionObservation
    verification_result: ActionVerificationResult
    corrective_action: RagAction | None = None
    budget_consumption: BudgetConsumption
    final_stop_reason: RagStopReason | None = None


class ProductRagLoopResult(RagModel):
    """Internal loop result; public answer/fallback mapping is deferred to T06."""

    target_scope: ObjectScope
    traces: tuple[ActionRoundTrace, ...] = Field(min_length=1, max_length=2)
    evidence_gate: EvidenceGateResult | None = None
    stop_reason: RagStopReason

    @model_validator(mode="after")
    def validate_trace_scopes(self) -> "ProductRagLoopResult":
        if any(
            trace.action_plan.target_scope != self.target_scope for trace in self.traces
        ):
            raise ValueError("Product RAG action plans cannot mutate target identity")
        if self.traces[-1].final_stop_reason != self.stop_reason:
            raise ValueError("final trace must carry the loop stop reason")
        return self


class BoundedProductRagLoop:
    """Run one baseline retrieval and at most one scoped corrective action."""

    def __init__(
        self,
        *,
        retriever: ProductRagRetriever,
        budget: ProductRagBudget | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._retriever = retriever
        self._budget = budget or ProductRagBudget()
        self._clock_ms = clock_ms or _monotonic_ms

    def run(
        self,
        *,
        request: RetrievalRequest,
        claim: RagClaim,
        corrective_action: RagAction = RagAction.TARGETED_RETRIEVAL,
    ) -> ProductRagLoopResult:
        """Evaluate a single claim without changing its scope or using commerce."""
        if claim.scope != request.turn_target:
            raise ValueError("claim scope must equal the retrieval target")
        if corrective_action not in {
            RagAction.TARGETED_RETRIEVAL,
            RagAction.REQUEST_CLARIFICATION,
        }:
            raise ValueError(
                "corrective action must be targeted retrieval or clarification"
            )

        started_at = self._clock_ms()
        traces: list[ActionRoundTrace] = []
        consumption = BudgetConsumption(
            action_rounds=0, tool_calls=0, retrieval_tokens=0
        )

        baseline = self._retrieve(request)
        consumption = _consume_retrieval(consumption, baseline)
        gate = gate_retrieval_evidence(baseline, claims=(claim,))

        if _deadline_exhausted(started_at, self._clock_ms(), self._budget):
            return self._finish(
                traces,
                plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                observation=_observation(baseline),
                gate=gate,
                consumption=consumption,
                stop_reason=RagStopReason.TURN_DEADLINE,
            )
        if consumption.retrieval_tokens > self._budget.max_retrieval_tokens:
            return self._finish(
                traces,
                plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                observation=_observation(baseline),
                gate=gate,
                consumption=consumption,
                stop_reason=RagStopReason.RETRIEVAL_TOKEN_BUDGET,
            )
        if gate.accepted_claim_ids:
            return self._finish(
                traces,
                plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                observation=_observation(baseline),
                gate=gate,
                consumption=consumption,
                stop_reason=RagStopReason.EVIDENCE_ACCEPTED,
            )
        if _requires_dynamic_fact(gate):
            return self._finish(
                traces,
                plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                observation=_observation(baseline),
                gate=gate,
                consumption=consumption,
                stop_reason=RagStopReason.DYNAMIC_FACT_REQUIRED,
            )
        if self._budget.max_action_rounds == 1:
            return self._finish(
                traces,
                plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                observation=_observation(baseline),
                gate=gate,
                consumption=consumption,
                stop_reason=RagStopReason.ACTION_ROUND_LIMIT,
            )
        if consumption.tool_calls >= self._budget.max_tool_calls:
            return self._finish(
                traces,
                plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                observation=_observation(baseline),
                gate=gate,
                consumption=consumption,
                stop_reason=RagStopReason.TOOL_CALL_LIMIT,
            )
        if corrective_action is RagAction.REQUEST_CLARIFICATION:
            traces.append(
                _trace(
                    plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                    observation=_observation(baseline),
                    gate=gate,
                    consumption=consumption,
                    corrective_action=RagAction.REQUEST_CLARIFICATION,
                )
            )
            clarification_plan = ActionPlan(
                round_number=2,
                action=RagAction.REQUEST_CLARIFICATION,
                target_scope=request.turn_target,
                reason="Evidence is insufficient; request a same-target clarification.",
            )
            return self._finish(
                traces,
                plan=clarification_plan,
                observation=ActionObservation(evidence_count=0),
                gate=None,
                consumption=BudgetConsumption(
                    action_rounds=2,
                    tool_calls=consumption.tool_calls,
                    retrieval_tokens=consumption.retrieval_tokens,
                ),
                stop_reason=RagStopReason.CLARIFICATION_REQUIRED,
            )

        traces.append(
            _trace(
                plan=_plan(1, RagAction.BASELINE_RETRIEVAL, request.turn_target),
                observation=_observation(baseline),
                gate=gate,
                consumption=consumption,
                corrective_action=RagAction.TARGETED_RETRIEVAL,
            )
        )
        targeted_request = request.model_copy(update={"field_hint": claim.field})
        targeted = self._retrieve(targeted_request)
        consumption = _consume_retrieval(consumption, targeted)
        gate = gate_retrieval_evidence(targeted, claims=(claim,))
        if _deadline_exhausted(started_at, self._clock_ms(), self._budget):
            stop_reason = RagStopReason.TURN_DEADLINE
        elif consumption.retrieval_tokens > self._budget.max_retrieval_tokens:
            stop_reason = RagStopReason.RETRIEVAL_TOKEN_BUDGET
        elif gate.accepted_claim_ids:
            stop_reason = RagStopReason.EVIDENCE_ACCEPTED
        elif _requires_dynamic_fact(gate):
            stop_reason = RagStopReason.DYNAMIC_FACT_REQUIRED
        else:
            stop_reason = RagStopReason.ACTION_ROUND_LIMIT
        return self._finish(
            traces,
            plan=ActionPlan(
                round_number=2,
                action=RagAction.TARGETED_RETRIEVAL,
                target_scope=request.turn_target,
                reason="Baseline evidence was insufficient; run one scoped field hint.",
            ),
            observation=_observation(targeted),
            gate=gate,
            consumption=consumption,
            stop_reason=stop_reason,
        )

    def _retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        return self._retriever.retrieve(request)

    def _finish(
        self,
        traces: list[ActionRoundTrace],
        *,
        plan: ActionPlan,
        observation: ActionObservation,
        gate: EvidenceGateResult | None,
        consumption: BudgetConsumption,
        stop_reason: RagStopReason,
    ) -> ProductRagLoopResult:
        if gate is not None and stop_reason in {
            RagStopReason.TURN_DEADLINE,
            RagStopReason.RETRIEVAL_TOKEN_BUDGET,
        }:
            gate = reject_for_budget(gate)
        traces.append(
            _trace(
                plan=plan,
                observation=observation,
                gate=gate,
                consumption=consumption,
                final_stop_reason=stop_reason,
            )
        )
        return ProductRagLoopResult(
            target_scope=plan.target_scope,
            traces=tuple(traces),
            evidence_gate=gate,
            stop_reason=stop_reason,
        )


def _plan(round_number: int, action: RagAction, scope: ObjectScope) -> ActionPlan:
    return ActionPlan(
        round_number=round_number,
        action=action,
        target_scope=scope,
        reason="Start baseline retrieval for the fixed Product RAG target.",
    )


def _trace(
    *,
    plan: ActionPlan,
    observation: ActionObservation,
    gate: EvidenceGateResult | None,
    consumption: BudgetConsumption,
    corrective_action: RagAction | None = None,
    final_stop_reason: RagStopReason | None = None,
) -> ActionRoundTrace:
    return ActionRoundTrace(
        action_plan=plan,
        choice_reason=plan.reason,
        observation=observation,
        verification_result=(
            ActionVerificationResult.ACCEPTED
            if gate is not None and gate.accepted_claim_ids
            else (
                ActionVerificationResult.REJECTED
                if gate is not None
                else ActionVerificationResult.NOT_RUN
            )
        ),
        corrective_action=corrective_action,
        budget_consumption=consumption,
        final_stop_reason=final_stop_reason,
    )


def _observation(result: RetrievalResult) -> ActionObservation:
    return ActionObservation(
        evidence_count=len(result.evidence), missing_reason=result.missing_reason
    )


def _consume_retrieval(
    consumption: BudgetConsumption, result: RetrievalResult
) -> BudgetConsumption:
    return BudgetConsumption(
        action_rounds=consumption.action_rounds + 1,
        tool_calls=consumption.tool_calls + 1,
        retrieval_tokens=consumption.retrieval_tokens
        + sum(len(chunk.text.split()) for chunk in result.evidence),
    )


def _requires_dynamic_fact(gate: EvidenceGateResult) -> bool:
    return any(
        fallback.reason is RagFallbackReason.DYNAMIC_FACT_REQUIRED
        for fallback in gate.fallbacks
    )


def _deadline_exhausted(started_at: int, now: int, budget: ProductRagBudget) -> bool:
    return now - started_at >= budget.turn_deadline_ms


def _monotonic_ms() -> int:
    return int(monotonic() * 1000)


__all__ = [
    "ActionObservation",
    "ActionPlan",
    "ActionRoundTrace",
    "ActionVerificationResult",
    "BoundedProductRagLoop",
    "BudgetConsumption",
    "ProductRagBudget",
    "ProductRagLoopResult",
    "ProductRagRetriever",
    "RagAction",
    "RagStopReason",
]
