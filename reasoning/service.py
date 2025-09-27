"""Reasoning orchestrator placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from common.contracts import (
    EventMeta,
    ReasoningAnalysisProposed,
    RetrievalContextBundle,
)


@dataclass(slots=True, kw_only=True)
class ReasoningConfig:
    """Configuration for reasoning agents."""

    planner: str
    max_tokens: int = 2048


class ReasoningService:
    """Synthesises evidence and produces proposed analyses."""

    def __init__(self, config: ReasoningConfig) -> None:
        self._config = config

    def analyse(
        self, context: RetrievalContextBundle, meta: EventMeta
    ) -> ReasoningAnalysisProposed:
        """Generate a candidate analysis from retrieved context."""

        raise NotImplementedError("Reasoning service has not been implemented")
