"""Hybrid retrieval backends and rerankers."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Protocol, cast

from common.contracts import IngestionNormalised, RetrievedPassage

try:  # pragma: no cover - exercised indirectly
    from rapidfuzz import fuzz  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - fallback when dependency missing

    class _FuzzFallback:
        @staticmethod
        def partial_ratio(a: str, b: str) -> int:
            return int(SequenceMatcher(None, a, b).ratio() * 100)

    fuzz = _FuzzFallback()

logger = logging.getLogger(__name__)


def _require_module(module: str, requirement: str) -> Any:
    """Import ``module`` or raise a runtime error referencing ``requirement``."""

    if importlib.util.find_spec(module) is None:
        raise RuntimeError(f"{requirement} is required for this backend")
    return importlib.import_module(module)


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
    reranker: KeywordOverlapReranker | CrossEncoderReranker | None = None
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


class EmbeddingModel(Protocol):
    """Protocol describing embedding providers."""

    def encode(self, text: str) -> list[float]:
        ...


@dataclass(slots=True)
class HashingEmbedder:
    """Hashing-based embedder suitable for bootstrap flows."""

    dimension: int = 768

    def encode(self, text: str) -> list[float]:
        tokens = [token for token in text.lower().split() if token]
        vector = [0.0] * self.dimension
        for token in tokens:
            index = hash(token) % self.dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


@dataclass(slots=True)
class SentenceTransformerEmbedder:
    """Sentence-Transformers embedder with optional lazy model injection."""

    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str | None = None
    normalize: bool = True
    _model: Any | None = None

    def __post_init__(self) -> None:  # pragma: no cover - import guarded
        if self._model is None:
            module = cast(
                Any, _require_module("sentence_transformers", "sentence-transformers")
            )
            self._model = module.SentenceTransformer(
                self.model_name, device=self.device
            )

    def encode(self, text: str) -> list[float]:
        if self._model is None:  # pragma: no cover - safety net
            raise RuntimeError("SentenceTransformer model failed to initialise")
        embeddings = self._model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=self.normalize,
        )
        return embeddings[0].tolist()


class QdrantVectorBackend(VectorBackend):
    """Vector backend backed by a Qdrant collection."""

    def __init__(
        self,
        *,
        collection_name: str,
        vector_size: int = 768,
        location: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        prefer_grpc: bool = False,
        embedder: EmbeddingModel | None = None,
        client: Any | None = None,
    ) -> None:
        if client is None:
            qdrant_client = cast(
                Any, _require_module("qdrant_client", "qdrant-client")
            )
            rest = cast(
                Any, _require_module("qdrant_client.http.models", "qdrant-client")
            )
            connection: dict[str, Any] = {"prefer_grpc": prefer_grpc}
            if url:
                connection["url"] = url
                if api_key:
                    connection["api_key"] = api_key
            else:
                connection["location"] = location or ":memory:"
            client = qdrant_client.QdrantClient(**connection)
            self._rest = rest
        else:
            from types import SimpleNamespace

            # Provide minimal rest compatibility for tests when injecting a stub client.
            self._rest = SimpleNamespace(
                Batch=lambda ids, vectors, payloads: {  # type: ignore[misc]
                    "ids": ids,
                    "vectors": vectors,
                    "payloads": payloads,
                },
                Distance=SimpleNamespace(COSINE="Cosine"),
                VectorParams=lambda size, distance: {  # type: ignore[misc]
                    "size": size,
                    "distance": distance,
                },
            )
        self._client = cast(Any, client)
        self._collection = collection_name
        self._vector_size = vector_size
        self._embedder = embedder or HashingEmbedder(dimension=vector_size)
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
            vector = self._embedder.encode(body)
            document_id = document.canonical_uri
            vectors.append(vector)
            ids.append(document_id)
            payloads.append(
                {
                    "uri": document.canonical_uri,
                    "snippet": body[:500],
                    "metadata": document.provenance,
                }
            )
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
        vector = self._embedder.encode(query)
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=limit,
        )
        passages: list[RetrievedPassage] = []
        for hit in hits:
            payload = getattr(hit, "payload", None) or {}
            uri = payload.get("uri", "vector")
            snippet = payload.get("snippet", uri)
            passages.append(
                RetrievedPassage(
                    source_id="qdrant",
                    snippet=snippet,
                    score=float(getattr(hit, "score", 0.0) or 0.0),
                    metadata={"uri": uri} | payload.get("metadata", {}),
                )
            )
        return passages

    def _ensure_collection(self) -> None:
        if hasattr(self._client, "collection_exists"):
            exists = self._client.collection_exists(self._collection)
        else:  # pragma: no cover - injected stub path
            exists = False
        if exists:
            return
        if hasattr(self._client, "create_collection"):
            params = self._rest.VectorParams(
                size=self._vector_size,
                distance=self._rest.Distance.COSINE,
            )
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=params,
            )


@dataclass(slots=True)
class OpenSearchLexicalBackend(LexicalBackend):
    """Lexical backend backed by an OpenSearch cluster."""

    index_name: str
    hosts: Sequence[str]
    username: str | None = None
    password: str | None = None
    use_ssl: bool = False
    verify_certs: bool = True
    ca_certs: str | None = None
    client: Any | None = None

    def __post_init__(self) -> None:  # pragma: no cover - import guarded
        self._helpers: Any | None = None
        if self.client is None:
            module = cast(Any, _require_module("opensearchpy", "opensearch-py"))
            helpers = module.helpers
            auth = None
            if self.username and self.password:
                auth = (self.username, self.password)
            self.client = module.OpenSearch(
                hosts=list(self.hosts),
                http_auth=auth,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                ca_certs=self.ca_certs,
            )
            self._helpers = helpers
        else:
            self._helpers = getattr(self.client, "helpers", None)
        self.client = cast(Any, self.client)
        self._ensure_index()

    def index(self, documents: Iterable[IngestionNormalised]) -> None:
        actions = []
        client: Any = self.client
        for document in documents:
            content = document.provenance.get("content", "")
            if not content:
                continue
            actions.append(
                {
                    "_op_type": "index",
                    "_index": self.index_name,
                    "_id": document.canonical_uri,
                    "_source": {
                        "uri": document.canonical_uri,
                        "content": content,
                        "metadata": document.provenance,
                    },
                }
            )
        if not actions:
            return
        if self._helpers and hasattr(self._helpers, "bulk"):
            self._helpers.bulk(client, actions)
        else:
            for action in actions:
                body = action["_source"]
                client.index(index=self.index_name, id=action["_id"], document=body)

    def search(self, query: str, limit: int) -> list[RetrievedPassage]:
        client: Any = self.client
        response = client.search(
            index=self.index_name,
            body={
                "size": limit,
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["content^3", "metadata.description^2", "metadata.*"],
                    }
                },
                "highlight": {"fields": {"content": {"fragment_size": 300}}},
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        passages: list[RetrievedPassage] = []
        for hit in hits:
            source = hit.get("_source", {})
            metadata = source.get("metadata", {})
            snippet = "".join(hit.get("highlight", {}).get("content", [])) or source.get(
                "content",
                "",
            )
            passages.append(
                RetrievedPassage(
                    source_id="opensearch",
                    snippet=snippet[:500],
                    score=float(hit.get("_score", 0.0)),
                    metadata={"uri": source.get("uri", ""), **metadata},
                )
            )
        return passages

    def _ensure_index(self) -> None:
        client: Any = self.client
        if client.indices.exists(index=self.index_name):
            return
        settings = {
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                }
            },
            "mappings": {
                "properties": {
                    "content": {"type": "text"},
                    "metadata": {"type": "object", "enabled": True},
                    "uri": {"type": "keyword"},
                }
            },
        }
        client.indices.create(index=self.index_name, body=settings)


@dataclass(slots=True)
class CrossEncoderReranker:
    """Sentence-Transformers cross-encoder reranker."""

    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    batch_size: int = 16
    max_length: int | None = None
    device: str | None = None
    _model: Any | None = None

    def __post_init__(self) -> None:  # pragma: no cover - import guarded
        if self._model is None:
            module = cast(
                Any, _require_module("sentence_transformers", "sentence-transformers")
            )
            self._model = module.CrossEncoder(
                self.model_name, device=self.device
            )

    def rerank(
        self,
        query: str,
        passages: Sequence[RetrievedPassage],
        limit: int,
    ) -> list[RetrievedPassage]:
        if not passages:
            return []
        pairs = [(query, passage.snippet) for passage in passages]
        scores = self._model.predict(  # type: ignore[no-any-return]
            pairs,
            batch_size=self.batch_size,
            max_length=self.max_length,
        )
        scored = list(zip(scores, passages, strict=False))
        scored.sort(key=lambda item: float(item[0]), reverse=True)
        ranked = [passage for _, passage in scored]
        return ranked[:limit]


def build_hybrid_backend(config: dict[str, Any], max_results: int) -> HybridRetrieverBackend:
    """Build a hybrid backend from configuration."""

    lexical_config = config.get("lexical", {})
    vector_config = config.get("vector", {})
    reranker_config = config.get("reranker", {})

    lexical_backend: LexicalBackend | None = None
    lexical_backend_type = lexical_config.get("backend", "rapidfuzz")
    if lexical_backend_type == "rapidfuzz":
        lexical_backend = RapidFuzzLexicalBackend()
    elif lexical_backend_type == "opensearch":
        try:
            lexical_backend = OpenSearchLexicalBackend(
                index_name=lexical_config.get("index", "prometheus-docs"),
                hosts=tuple(
                    lexical_config.get("hosts", ("http://localhost:9200",))
                ),
                username=lexical_config.get("username"),
                password=lexical_config.get("password"),
                use_ssl=bool(lexical_config.get("use_ssl", False)),
                verify_certs=bool(lexical_config.get("verify_certs", True)),
                ca_certs=lexical_config.get("ca_certs"),
            )
        except Exception as exc:  # pragma: no cover - runtime degradation
            logger.warning(
                "OpenSearch backend unavailable (%s); falling back to RapidFuzz.",
                exc,
            )
            lexical_backend = RapidFuzzLexicalBackend()

    vector_backend: VectorBackend | None = None
    backend_type = vector_config.get("backend")
    if backend_type == "qdrant":
        embedder_config = vector_config.get("embedder", {})
        embedder: EmbeddingModel | None = None
        if embedder_config.get("type") == "sentence-transformer":
            embedder = SentenceTransformerEmbedder(
                model_name=embedder_config.get(
                    "model_name", "sentence-transformers/all-MiniLM-L6-v2"
                ),
                device=embedder_config.get("device"),
                normalize=bool(embedder_config.get("normalize", True)),
            )
        vector_backend = QdrantVectorBackend(
            collection_name=vector_config.get("collection", "prometheus"),
            vector_size=int(vector_config.get("vector_size", 768)),
            location=vector_config.get("location"),
            url=vector_config.get("url"),
            api_key=vector_config.get("api_key"),
            prefer_grpc=bool(vector_config.get("prefer_grpc", False)),
            embedder=embedder,
        )

    reranker: KeywordOverlapReranker | CrossEncoderReranker | None = None
    reranker_strategy = reranker_config.get("strategy", "keyword_overlap")
    if reranker_strategy == "keyword_overlap":
        reranker = KeywordOverlapReranker(
            min_overlap=int(reranker_config.get("min_overlap", 1))
        )
    elif reranker_strategy == "cross_encoder":
        reranker = CrossEncoderReranker(
            model_name=reranker_config.get(
                "model_name", "cross-encoder/ms-marco-MiniLM-L-6-v2"
            ),
            batch_size=int(reranker_config.get("batch_size", 16)),
            max_length=reranker_config.get("max_length"),
            device=reranker_config.get("device"),
        )

    return HybridRetrieverBackend(
        lexical=lexical_backend,
        vector=vector_backend,
        reranker=reranker,
        max_results=max_results,
    )

