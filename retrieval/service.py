"""Hybrid retrieval orchestration surface."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from common.contracts import EventMeta, RetrievalContextBundle, RetrievedPassage


class Retriever(Protocol):
    """Protocol for pluggable retrievers."""

    def retrieve(self, query: str) -> Iterable[RetrievedPassage]:
        """Execute the retrieval strategy for a query."""

        ...


@dataclass(slots=True, kw_only=True)
class RetrievalConfig:
    """Configuration for the retrieval stage."""

    strategy: str
    max_results: int = 20


class RetrievalService:
    """Coordinates lexical/vector retrievers and reranking."""

    def __init__(self, config: RetrievalConfig, retriever: Retriever) -> None:
        self._config = config
        self._retriever = retriever

    def build_context(self, query: str, meta: EventMeta) -> RetrievalContextBundle:
        """Produce the context bundle forwarded to reasoning."""

        passages = list(self._retriever.retrieve(query))
        return RetrievalContextBundle(
            meta=meta,
            query=query,
            strategy={"name": self._config.strategy},
            passages=passages,
        )
