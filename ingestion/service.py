"""Primary orchestration surface for the ingestion stage."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.contracts import AttachmentManifest, IngestionNormalised
from common.events import EventFactory

from .connectors import SourceConnector, build_connector
from .models import IngestionPayload
from .persistence import DocumentStore, InMemoryDocumentStore, SQLiteDocumentStore
from .pii import PIIRedactor, RedactionResult
from .scheduler import IngestionScheduler


@dataclass(slots=True, kw_only=True)
class IngestionConfig:
    """Minimal configuration contract for ingestion services."""

    sources: list[dict[str, Any]]
    persistence: dict[str, Any] | None = None
    scheduler: SchedulerConfig | dict[str, Any] | None = None
    redaction: RedactionConfig | dict[str, Any] | None = None

    def __post_init__(self) -> None:
        scheduler = self.scheduler or SchedulerConfig()
        redaction = self.redaction or RedactionConfig()
        if isinstance(scheduler, dict):
            scheduler = SchedulerConfig(**scheduler)
        if isinstance(redaction, dict):
            redaction = RedactionConfig(**redaction)
        object.__setattr__(self, "scheduler", scheduler)
        object.__setattr__(self, "redaction", redaction)


@dataclass(slots=True, kw_only=True)
class SchedulerConfig:
    """Configuration for the asynchronous ingestion scheduler."""

    concurrency: int = 4
    rate_limit_per_second: float | None = None
    max_retries: int = 2
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 5.0
    jitter_seconds: float = 0.25


@dataclass(slots=True, kw_only=True)
class RedactionConfig:
    """Configuration for the PII redaction pipeline."""

    enabled: bool = True
    language: str = "en"
    placeholder: str = "[REDACTED]"


class IngestionService:
    """Normalises raw inputs into shared documents.

    The real implementation will surface async collection, rate limiting, and
    source-specific adapters. For now we just expose a synchronous signature so
    downstream stages can depend on a stable interface while we bootstrap the
    modules.
    """

    def __init__(
        self,
        config: IngestionConfig,
        *,
        connectors: Sequence[SourceConnector] | None = None,
        store: DocumentStore | None = None,
        redactor: PIIRedactor | None = None,
    ) -> None:
        self._config = config
        self._connectors = list(connectors) if connectors else self._build_connectors()
        self._store = store or self._build_store()
        self._redactor = redactor or PIIRedactor(
            enabled=config.redaction.enabled,
            language=config.redaction.language,
            placeholder=config.redaction.placeholder,
        )

    @property
    def connectors(self) -> Sequence[SourceConnector]:
        """Return the configured connectors for inspection/testing."""

        return self._connectors

    def collect(self) -> list[IngestionPayload]:
        """Gather raw payloads from configured sources."""

        return asyncio.run(self.collect_async())

    async def collect_async(self) -> list[IngestionPayload]:
        """Asynchronously gather payloads from configured connectors."""

        scheduler = IngestionScheduler(
            self._connectors,
            concurrency=self._config.scheduler.concurrency,
            max_retries=self._config.scheduler.max_retries,
            initial_backoff=self._config.scheduler.initial_backoff_seconds,
            max_backoff=self._config.scheduler.max_backoff_seconds,
            jitter=self._config.scheduler.jitter_seconds,
            rate_limit_per_second=self._config.scheduler.rate_limit_per_second,
        )
        return await scheduler.run()

    def normalise(
        self,
        payloads: Iterable[IngestionPayload],
        factory: EventFactory,
    ) -> list[IngestionNormalised]:
        """Convert raw references into structured documents."""

        normalised: list[IngestionNormalised] = []
        for payload in payloads:
            redacted = self._apply_redaction(payload.content)
            meta = factory.create_meta(event_name="ingestion.normalised")
            checksum = hashlib.sha256(redacted.text.encode("utf-8")).hexdigest()
            document_id = self._store.persist(
                payload.reference.uri,
                redacted.text,
                self._build_metadata(payload.metadata, checksum, redacted),
            )
            attachment = AttachmentManifest(
                uri=f"documentstore://{document_id}",
                content_type="text/plain",
                byte_size=len(redacted.text.encode("utf-8")),
                checksum=checksum,
            )
            provenance = self._build_provenance(payload, redacted)
            normalised.append(
                IngestionNormalised(
                    meta=meta,
                    source_system=payload.reference.source_id,
                    canonical_uri=payload.reference.uri,
                    provenance=provenance,
                    attachments=[attachment],
                    evidence=[payload.reference],
                    pii_redactions=redacted.entities,
                )
            )
        return normalised

    def _build_connectors(self) -> list[SourceConnector]:
        return [build_connector(config) for config in self._config.sources]

    def _build_store(self) -> DocumentStore:
        persistence = self._config.persistence or {"type": "memory"}
        store_type = persistence.get("type", "memory")
        if store_type == "sqlite":
            path = Path(persistence.get("path", "var/ingestion.db")).expanduser().resolve()
            return SQLiteDocumentStore(path)
        return InMemoryDocumentStore()

    def _apply_redaction(self, content: str) -> RedactionResult:
        return self._redactor.redact(content)

    def _build_metadata(
        self,
        metadata: dict[str, str],
        checksum: str,
        redacted: RedactionResult,
    ) -> dict[str, str]:
        payload = dict(metadata)
        payload["checksum"] = checksum
        payload["pii_redacted"] = str(bool(redacted.findings)).lower()
        if redacted.findings:
            payload["pii_entities"] = ",".join(redacted.entities)
        return payload

    def _build_provenance(
        self,
        payload: IngestionPayload,
        redacted: RedactionResult,
    ) -> dict[str, str]:
        provenance = {
            "description": payload.reference.description or "",
            "content": redacted.text,
            "pii_redacted": str(bool(redacted.findings)).lower(),
        }
        if redacted.findings:
            provenance["pii_entities"] = ",".join(redacted.entities)
        provenance.update(payload.metadata)
        return provenance
