"""Retrieval stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class RetrievedPassage:
    """Structured passage returned from hybrid retrieval."""

    source_id: str
    snippet: str
    score: float
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class RetrievalContextBundle(BaseEvent):
    """Bundle of evidence provided to the reasoning stage."""

    query: str
    strategy: Dict[str, str] = field(default_factory=dict)
    passages: List[RetrievedPassage] = field(default_factory=list)
