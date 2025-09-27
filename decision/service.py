"""Decision stage guardrail surface."""

from __future__ import annotations

from dataclasses import dataclass

from common.contracts import (
    DecisionRecorded,
    EventMeta,
    ReasoningAnalysisProposed,
)


@dataclass(slots=True, kw_only=True)
class DecisionConfig:
    """Configuration for policy enforcement."""

    policy_engine: str


class DecisionService:
    """Validates proposed analyses against policies and produces decisions."""

    def __init__(self, config: DecisionConfig) -> None:
        self._config = config

    def evaluate(
        self, proposal: ReasoningAnalysisProposed, meta: EventMeta
    ) -> DecisionRecorded:
        """Run policy evaluation and return a recorded decision."""

        status = "approved" if proposal.recommended_actions else "needs_review"
        rationale = proposal.summary
        alternatives = [
            "Manual review",
            "Request additional evidence",
        ]
        policy_checks = {
            "engine": self._config.policy_engine,
            "insight_count": str(len(proposal.insights)),
        }
        return DecisionRecorded(
            meta=meta,
            decision_type="automated",
            status=status,
            rationale=rationale,
            alternatives=alternatives,
            policy_checks=policy_checks,
        )
