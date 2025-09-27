"""Reasoning orchestrator placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from common.contracts import (
    EventMeta,
    Insight,
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

        insights = [
            Insight(
                text=passage.snippet,
                confidence=min(passage.score, 1.0),
                assumptions=[],
            )
            for passage in context.passages
        ]
        summary = self._summarise(context)
        actions = [f"Review evidence from {len(context.passages)} passages"]
        metadata = {"planner": self._config.planner}
        unresolved = [] if context.passages else ["No supporting evidence"]
        return ReasoningAnalysisProposed(
            meta=meta,
            summary=summary,
            recommended_actions=actions,
            insights=insights,
            unresolved_questions=unresolved,
            metadata=metadata,
        )

    def _summarise(self, context: RetrievalContextBundle) -> str:
        passage_count = len(context.passages)
        return (
            f"Synthesised {passage_count} passages for query "
            f"'{context.query}'."
        )
