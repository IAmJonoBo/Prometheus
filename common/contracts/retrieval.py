"""Retrieval stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class RetrievedPassage:
    """Structured passage returned from hybrid retrieval."""

    source_id: str
    snippet: str
    score: float
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class RetrievalContextBundle(BaseEvent):
    """Bundle of evidence provided to the reasoning stage."""

    query: str
    strategy: dict[str, str] = field(default_factory=dict)
    passages: list[RetrievedPassage] = field(default_factory=list)
