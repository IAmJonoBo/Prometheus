"""Tests for retrieval backends and rerankers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from common.contracts import EventMeta, IngestionNormalised, RetrievedPassage
from retrieval.backends import (
    CrossEncoderReranker,
    HashingEmbedder,
    OpenSearchLexicalBackend,
    QdrantVectorBackend,
    RapidFuzzLexicalBackend,
    build_hybrid_backend,
)


def _document(uri: str, content: str) -> IngestionNormalised:
    meta = EventMeta(
        event_id=f"event-{uri}",
        correlation_id="test",
        occurred_at=datetime.now(timezone.utc),  # noqa: UP017
    )
    return IngestionNormalised(
        meta=meta,
        source_system="memory",
        canonical_uri=uri,
        provenance={"content": content},
    )


class _StubQdrantClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.upserts: list[dict[str, Any]] = []
        self._collections: set[str] = set()

    def collection_exists(self, name: str) -> bool:
        return name in self._collections

    def create_collection(self, collection_name: str, vectors_config: object) -> None:
        self._collections.add(collection_name)
        self.created.append((collection_name, {"vectors_config": vectors_config}))

    def upsert(self, *, collection_name: str, points: dict[str, Any]) -> None:
        self.upserts.append({"collection": collection_name, "points": points})

    def search(self, *, collection_name: str, query_vector: list[float], limit: int) -> list[object]:
        hits = []
        for entry in self.upserts:
            for uri, vector in zip(entry["points"]["ids"], entry["points"]["vectors"], strict=False):
                hits.append(
                    SimpleNamespace(
                        payload={
                            "uri": uri,
                            "snippet": f"snippet-{uri}",
                            "metadata": {"vector": vector},
                        },
                        score=1.0,
                    )
                )
        return hits[:limit]


def test_qdrant_backend_indexes_and_searches() -> None:
    embedder = HashingEmbedder(dimension=4)
    client = _StubQdrantClient()
    backend = QdrantVectorBackend(
        collection_name="documents",
        vector_size=4,
        embedder=embedder,
        client=client,
    )

    documents = [_document("uri-1", "alpha beta"), _document("uri-2", "gamma delta")]
    backend.index(documents)

    assert client.upserts
    assert client.created[0][0] == "documents"

    results = backend.search("alpha", limit=5)
    assert results
    assert results[0].metadata["uri"] in {"uri-1", "uri-2"}
    assert results[0].source_id == "qdrant"


class _StubHelpers:
    def __init__(self) -> None:
        self.bulk_calls: list[tuple[object, list[dict[str, object]]]] = []

    def bulk(self, client: object, actions: list[dict[str, object]]) -> None:
        self.bulk_calls.append((client, actions))


class _StubOpenSearchClient:
    def __init__(self) -> None:
        self.indices = SimpleNamespace(
            exists=lambda index: False,
            create=lambda index, body: body,
        )
        self.helpers = _StubHelpers()
        self.indexed: list[tuple[str, str, dict[str, object]]] = []

    def index(self, *, index: str, id: str, document: dict[str, object]) -> None:
        self.indexed.append((index, id, document))

    def search(self, *, index: str, body: dict[str, object]) -> dict[str, object]:
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "uri-1",
                        "_score": 2.0,
                        "_source": {
                            "uri": "uri-1",
                            "content": "alpha beta",
                            "metadata": {"description": "Alpha"},
                        },
                        "highlight": {"content": ["alpha <em>beta</em>"]},
                    }
                ]
            }
        }


def test_opensearch_backend_indexes_and_searches() -> None:
    client = _StubOpenSearchClient()
    backend = OpenSearchLexicalBackend(
        index_name="documents",
        hosts=("http://localhost:9200",),
        client=client,
    )

    documents = [_document("uri-1", "alpha beta")]
    backend.index(documents)

    assert client.helpers.bulk_calls

    results = backend.search("alpha", limit=5)
    assert results[0].source_id == "opensearch"
    assert results[0].metadata["uri"] == "uri-1"
    assert "alpha" in results[0].snippet


class _StubCrossEncoder:
    def predict(self, pairs, batch_size=None, max_length=None):  # type: ignore[no-untyped-def]
        return [len(text) for _, text in pairs]


def test_cross_encoder_reranker_prefers_longer_snippets() -> None:
    reranker = CrossEncoderReranker(_model=_StubCrossEncoder())
    passages = [
        RetrievedPassage(source_id="a", snippet="short", score=0.3, metadata={"uri": "1"}),
        RetrievedPassage(source_id="b", snippet="a little bit longer", score=0.2, metadata={"uri": "2"}),
    ]

    ranked = reranker.rerank("query", passages, limit=2)
    assert ranked[0].metadata["uri"] == "2"


def test_build_hybrid_backend_falls_back_when_opensearch_unreachable(caplog) -> None:
    with patch(
        "retrieval.backends.OpenSearchLexicalBackend",
        side_effect=RuntimeError("connection failed"),
    ):
        with caplog.at_level(logging.WARNING):
            backend = build_hybrid_backend({"lexical": {"backend": "opensearch"}}, 5)

    assert isinstance(backend.lexical, RapidFuzzLexicalBackend)
    assert "falling back to RapidFuzz" in caplog.text
