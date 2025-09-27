"""Hybrid retrieval orchestration surface."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from common.contracts import (
    EventMeta,
    IngestionNormalised,
    RetrievalContextBundle,
    RetrievedPassage,
)

from .backends import HybridRetrieverBackend, build_hybrid_backend


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
    lexical: dict[str, Any] | None = None
    vector: dict[str, Any] | None = None
    reranker: dict[str, Any] | None = None


@runtime_checkable
class _SupportsIngest(Protocol):
    def ingest(self, documents: Iterable[IngestionNormalised]) -> None:
        ...


class RetrievalService:
    """Coordinates lexical/vector retrievers and reranking."""

    def __init__(self, config: RetrievalConfig, retriever: Retriever) -> None:
        self._config = config
        self._retriever = retriever

    def ingest(self, documents: Iterable[IngestionNormalised]) -> None:
        """Pass documents to the underlying retriever when supported."""

        if isinstance(self._retriever, _SupportsIngest):
            self._retriever.ingest(documents)

    def build_context(self, query: str, meta: EventMeta) -> RetrievalContextBundle:
        """Produce the context bundle forwarded to reasoning."""

        passages = list(self._retriever.retrieve(query))
        return RetrievalContextBundle(
            meta=meta,
            query=query,
            strategy={"name": self._config.strategy},
            passages=passages,
        )


class InMemoryRetriever:
    """Simple retriever used for bootstrap and testing flows."""

    def __init__(self) -> None:
        self._passages: list[RetrievedPassage] = []

    def ingest(self, documents: Iterable[IngestionNormalised]) -> None:
        self._passages = [
            RetrievedPassage(
                source_id=document.source_system,
                snippet=document.provenance.get("description", document.canonical_uri),
                score=1.0,
                metadata={"uri": document.canonical_uri},
            )
            for document in documents
        ]

    def retrieve(self, query: str) -> Iterable[RetrievedPassage]:
        lowered = query.lower()
        for passage in self._passages:
            if not lowered or lowered in passage.snippet.lower():
                yield passage


class HybridRetriever:
    """Retriever backed by lexical, vector, and reranking components."""

    def __init__(self, backend: HybridRetrieverBackend) -> None:
        self._backend = backend

    def ingest(self, documents: Iterable[IngestionNormalised]) -> None:
        self._backend.ingest(documents)

    def retrieve(self, query: str) -> Iterable[RetrievedPassage]:
        return self._backend.retrieve(query)


def build_hybrid_retriever(config: RetrievalConfig) -> HybridRetriever:
    """Factory for the hybrid retriever strategy."""

    backend = build_hybrid_backend(
        {
            "lexical": config.lexical or {},
            "vector": config.vector or {},
            "reranker": config.reranker or {},
        },
        config.max_results,
    )
    return HybridRetriever(backend)
