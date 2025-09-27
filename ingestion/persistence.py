"""Persistence backends for normalised ingestion artefacts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class DocumentStore:
    """Abstract persistence layer for ingestion outputs."""

    def persist(self, canonical_uri: str, content: str, metadata: dict[str, str]) -> str:
        """Persist a normalised document and return its identifier."""

        raise NotImplementedError


@dataclass(slots=True)
class InMemoryDocumentStore(DocumentStore):
    """Document store that retains artefacts in memory."""

    documents: dict[str, dict[str, Any]] = field(default_factory=dict)

    def persist(self, canonical_uri: str, content: str, metadata: dict[str, str]) -> str:
        document_id = str(uuid4())
        self.documents[document_id] = {
            "canonical_uri": canonical_uri,
            "content": content,
            "metadata": metadata,
            "created_at": datetime.now(UTC).isoformat(),
        }
        return document_id


@dataclass(slots=True)
class SQLiteDocumentStore(DocumentStore):
    """SQLite-backed document persistence."""

    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    canonical_uri TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def persist(self, canonical_uri: str, content: str, metadata: dict[str, str]) -> str:
        document_id = str(uuid4())
        payload = json.dumps(metadata, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO documents (id, canonical_uri, content, metadata, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    document_id,
                    canonical_uri,
                    content,
                    payload,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
        return document_id

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

