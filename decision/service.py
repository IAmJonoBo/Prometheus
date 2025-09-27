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

        raise NotImplementedError("Decision evaluation has not been implemented")
