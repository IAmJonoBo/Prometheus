"""Tests for ingestion connectors, redaction, and persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from common.events import EventFactory
from ingestion.connectors import MemoryConnector, SourceConnector
from ingestion.models import IngestionPayload
from ingestion.pii import RedactionFinding, RedactionResult
from ingestion.service import IngestionConfig, IngestionService


def test_ingestion_service_persists_documents(tmp_path: Path) -> None:
    database_path = tmp_path / "ingestion.db"
    config = IngestionConfig(
        sources=[{"type": "memory", "uri": "memory://unit-test", "content": "Hello"}],
        persistence={"type": "sqlite", "path": str(database_path)},
    )
    service = IngestionService(config)

    payloads = service.collect()
    assert payloads

    factory = EventFactory(correlation_id="test-correlation")
    normalised = service.normalise(payloads, factory)

    assert normalised[0].attachments
    assert normalised[0].provenance["content"] == "Hello"

    with sqlite3.connect(database_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        assert rows is not None
        assert rows[0] == 1


class _StubRedactor:
    def __init__(self) -> None:
        self.calls = 0

    def redact(self, text: str) -> RedactionResult:
        self.calls += 1
        return RedactionResult(
            text="[[REDACTED]]",
            findings=[RedactionFinding(entity_type="EMAIL_ADDRESS", start=0, end=len(text), score=0.9)],
        )


class _FailingConnector(SourceConnector):
    def __init__(self) -> None:
        self.attempts = 0
        self._delegate = MemoryConnector(
            uri="memory://retry",
            content="Email: ops@example.com",
        )

    def collect(self) -> list[IngestionPayload]:
        self.attempts += 1
        if self.attempts < 2:
            raise RuntimeError("temporary failure")
        return list(self._delegate.collect())


def test_ingestion_service_applies_redaction() -> None:
    config = IngestionConfig(
        sources=[{"type": "memory", "uri": "memory://redact", "content": "email ops@example.com"}],
        scheduler={"concurrency": 1},
    )
    redactor = _StubRedactor()
    service = IngestionService(config, redactor=redactor)

    payloads = service.collect()
    factory = EventFactory(correlation_id="redaction")
    normalised = service.normalise(payloads, factory)

    assert redactor.calls == 1
    assert normalised[0].provenance["content"] == "[[REDACTED]]"
    assert normalised[0].provenance["pii_redacted"] == "true"
    assert normalised[0].pii_redactions == ["EMAIL_ADDRESS"]


def test_ingestion_scheduler_retries_transient_failures() -> None:
    failing = _FailingConnector()

    def _build_connectors(_: dict[str, str]) -> list[dict[str, str]]:
        return []

    config = IngestionConfig(
        sources=[{"type": "memory", "uri": "memory://noop"}],
        scheduler={
            "concurrency": 1,
            "max_retries": 3,
            "initial_backoff_seconds": 0.0,
            "max_backoff_seconds": 0.0,
            "jitter_seconds": 0.0,
        },
    )
    service = IngestionService(config, connectors=[failing])

    payloads = service.collect()

    assert payloads
    assert failing.attempts == 2


def test_ingestion_metrics_capture_scheduler_and_redaction() -> None:
    config = IngestionConfig(
        sources=[{"type": "memory", "uri": "memory://metrics", "content": "secret"}],
        scheduler={"concurrency": 1},
    )
    redactor = _StubRedactor()
    service = IngestionService(config, redactor=redactor)

    payloads = service.collect()

    metrics = service.metrics
    assert metrics is not None
    assert metrics.scheduler.connectors_total == 1
    assert metrics.payloads_total == 1

    factory = EventFactory(correlation_id="metrics")
    service.normalise(payloads, factory)

    metrics = service.metrics
    assert metrics is not None
    assert metrics.redaction.documents_redacted == 1
    assert metrics.redaction.entities_detected == 1


def test_ingestion_config_requires_sources() -> None:
    with pytest.raises(ValueError):
        IngestionConfig(sources=[])
