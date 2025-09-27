"""Hybrid retrieval backends and rerankers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from common.contracts import IngestionNormalised, RetrievedPassage


class LexicalBackend:
    """Base class for lexical search backends."""

    def index(self, documents: Iterable[IngestionNormalised]) -> None:
        raise NotImplementedError

    def search(self, query: str, limit: int) -> list[RetrievedPassage]:
        raise NotImplementedError


class VectorBackend:
    """Base class for vector search backends."""

    def index(self, documents: Iterable[IngestionNormalised]) -> None:
        raise NotImplementedError

    def search(self, query: str, limit: int) -> list[RetrievedPassage]:
        raise NotImplementedError


@dataclass(slots=True)
class RapidFuzzLexicalBackend(LexicalBackend):
    """Lexical backend powered by RapidFuzz similarity scoring."""

    _entries: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)

    def index(self, documents: Iterable[IngestionNormalised]) -> None:
        self._entries = []
        for document in documents:
            body = document.provenance.get("content", "")
            self._entries.append((document.canonical_uri, body, document.provenance))

    def search(self, query: str, limit: int) -> list[RetrievedPassage]:
        scored: list[tuple[float, RetrievedPassage]] = []
        for uri, body, provenance in self._entries:
            if not body:
                continue
            score = fuzz.partial_ratio(query, body)
            if score <= 0:
                continue
            scored.append(
                (
                    float(score) / 100.0,
                    RetrievedPassage(
                        source_id=provenance.get("path", uri),
                        snippet=body[:500],
                        score=float(score) / 100.0,
                        metadata={"uri": uri},
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [passage for _, passage in scored[:limit]]


@dataclass(slots=True)
class KeywordOverlapReranker:
    """Reranker that prioritises passages sharing tokens with the query."""

    min_overlap: int = 1

    def rerank(
        self,
        query: str,
        passages: Sequence[RetrievedPassage],
        limit: int,
    ) -> list[RetrievedPassage]:
        query_tokens = {token for token in query.lower().split() if token}
        scored: list[tuple[float, RetrievedPassage]] = []
        for passage in passages:
            tokens = {token for token in passage.snippet.lower().split() if token}
            overlap = len(query_tokens & tokens)
            adjusted = passage.score + math.log1p(overlap)
            scored.append((adjusted, passage))
        scored.sort(key=lambda item: item[0], reverse=True)
        ranked = [passage for _, passage in scored]
        if self.min_overlap <= 1:
            return ranked[:limit]
        filtered = [
            passage
            for passage in ranked
            if len(query_tokens & set(passage.snippet.lower().split())) >= self.min_overlap
        ]
        return (filtered or ranked)[:limit]


@dataclass(slots=True)
class HybridRetrieverBackend:
    """Coordinate lexical and vector backends for hybrid retrieval."""

    lexical: LexicalBackend | None = None
    vector: VectorBackend | None = None
    reranker: KeywordOverlapReranker | None = None
    max_results: int = 20

    def ingest(self, documents: Iterable[IngestionNormalised]) -> None:
        if self.lexical:
            self.lexical.index(documents)
        if self.vector:
            self.vector.index(documents)

    def retrieve(self, query: str) -> list[RetrievedPassage]:
        candidates: list[RetrievedPassage] = []
        if self.lexical:
            candidates.extend(self.lexical.search(query, self.max_results))
        if self.vector:
            candidates.extend(self.vector.search(query, self.max_results))
        if not candidates:
            return []
        if self.reranker:
            return self.reranker.rerank(query, candidates, self.max_results)
        candidates.sort(key=lambda passage: passage.score, reverse=True)
        return candidates[: self.max_results]


class QdrantVectorBackend(VectorBackend):
    """Vector backend backed by an in-process Qdrant collection."""

    def __init__(
        self,
        *,
        collection_name: str,
        location: str = ":memory:",
        vector_size: int = 768,
    ) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as rest
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "qdrant-client is required for the QdrantVectorBackend"
            ) from exc

        self._rest = rest
        self._client = QdrantClient(location=location, prefer_grpc=False)
        self._collection = collection_name
        self._vector_size = vector_size
        self._ensure_collection()
        self._embeddings: dict[str, list[float]] = {}

    def index(self, documents: Iterable[IngestionNormalised]) -> None:
        payloads = []
        vectors = []
        ids = []
        for document in documents:
            body = document.provenance.get("content", "")
            if not body:
                continue
            vector = self._embed(body)
            document_id = document.canonical_uri
            vectors.append(vector)
            ids.append(document_id)
            payloads.append({"uri": document.canonical_uri})
            self._embeddings[document_id] = vector
        if not payloads:
            return
        self._client.upsert(
            collection_name=self._collection,
            points=self._rest.Batch(
                ids=ids,
                vectors=vectors,
                payloads=payloads,
            ),
        )

    def search(self, query: str, limit: int) -> list[RetrievedPassage]:
        vector = self._embed(query)
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=limit,
        )
        passages: list[RetrievedPassage] = []
        for hit in hits:
            metadata = hit.payload or {}
            uri = metadata.get("uri", "vector")
            passages.append(
                RetrievedPassage(
                    source_id="qdrant",
                    snippet=uri,
                    score=float(hit.score or 0.0),
                    metadata={"uri": uri},
                )
            )
        return passages

    def _ensure_collection(self) -> None:
        from qdrant_client.http import models as rest

        if self._client.collection_exists(self._collection):
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=rest.VectorParams(size=self._vector_size, distance=rest.Distance.COSINE),
        )

    def _embed(self, text: str) -> list[float]:
        # Lightweight hashing-based embedding keeps the bootstrap dependency light.
        tokens = [token for token in text.lower().split() if token]
        vector = [0.0] * self._vector_size
        for token in tokens:
            index = hash(token) % self._vector_size
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def build_hybrid_backend(config: dict[str, Any], max_results: int) -> HybridRetrieverBackend:
    """Build a hybrid backend from configuration."""

    lexical_config = config.get("lexical", {})
    vector_config = config.get("vector", {})
    reranker_config = config.get("reranker", {})

    lexical_backend: LexicalBackend | None = None
    if lexical_config.get("backend", "rapidfuzz") == "rapidfuzz":
        lexical_backend = RapidFuzzLexicalBackend()

    vector_backend: VectorBackend | None = None
    backend_type = vector_config.get("backend")
    if backend_type == "qdrant":
        vector_backend = QdrantVectorBackend(
            collection_name=vector_config.get("collection", "prometheus"),
            location=vector_config.get("location", ":memory:"),
            vector_size=int(vector_config.get("vector_size", 768)),
        )

    reranker: KeywordOverlapReranker | None = None
    reranker_strategy = reranker_config.get("strategy", "keyword_overlap")
    if reranker_strategy == "keyword_overlap":
        reranker = KeywordOverlapReranker(
            min_overlap=int(reranker_config.get("min_overlap", 1))
        )

    return HybridRetrieverBackend(
        lexical=lexical_backend,
        vector=vector_backend,
        reranker=reranker,
        max_results=max_results,
    )

