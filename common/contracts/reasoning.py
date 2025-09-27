"""Reasoning stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class Insight:
    """Single insight or claim produced by reasoning agents."""

    text: str
    confidence: float
    assumptions: List[str] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class ReasoningAnalysisProposed(BaseEvent):
    """Proposed analysis forwarded to the decision stage."""

    summary: str
    recommended_actions: List[str] = field(default_factory=list)
    insights: List[Insight] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
