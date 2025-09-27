"""Tests for ingestion connectors and persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from common.events import EventFactory
from ingestion.service import IngestionConfig, IngestionService


def test_ingestion_service_persists_documents(tmp_path: Path) -> None:
    database_path = tmp_path / "ingestion.db"
    config = IngestionConfig(
        sources=[{"type": "memory", "uri": "memory://unit-test", "content": "Hello"}],
        persistence={"type": "sqlite", "path": str(database_path)},
    )
    service = IngestionService(config)

    payloads = list(service.collect())
    assert payloads

    factory = EventFactory(correlation_id="test-correlation")
    normalised = service.normalise(payloads, factory)

    assert normalised[0].attachments
    assert normalised[0].provenance["content"] == "Hello"

    with sqlite3.connect(database_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        assert rows is not None
        assert rows[0] == 1
