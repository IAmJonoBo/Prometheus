"""Primary orchestration surface for the ingestion stage."""

from __future__ import annotations

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


@dataclass(slots=True, kw_only=True)
class IngestionConfig:
    """Minimal configuration contract for ingestion services."""

    sources: list[dict[str, Any]]
    persistence: dict[str, Any] | None = None


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
    ) -> None:
        self._config = config
        self._connectors = list(connectors) if connectors else self._build_connectors()
        self._store = store or self._build_store()

    @property
    def connectors(self) -> Sequence[SourceConnector]:
        """Return the configured connectors for inspection/testing."""

        return self._connectors

    def collect(self) -> Iterable[IngestionPayload]:
        """Gather raw payloads from configured sources."""

        for connector in self._connectors:
            yield from connector.collect()

    def normalise(
        self,
        payloads: Iterable[IngestionPayload],
        factory: EventFactory,
    ) -> list[IngestionNormalised]:
        """Convert raw references into structured documents."""

        normalised: list[IngestionNormalised] = []
        for payload in payloads:
            meta = factory.create_meta(event_name="ingestion.normalised")
            checksum = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
            document_id = self._store.persist(
                payload.reference.uri,
                payload.content,
                {**payload.metadata, "checksum": checksum},
            )
            attachment = AttachmentManifest(
                uri=f"documentstore://{document_id}",
                content_type="text/plain",
                byte_size=len(payload.content.encode("utf-8")),
                checksum=checksum,
            )
            provenance = {
                "description": payload.reference.description or "",
                "content": payload.content,
                **payload.metadata,
            }
            normalised.append(
                IngestionNormalised(
                    meta=meta,
                    source_system=payload.reference.source_id,
                    canonical_uri=payload.reference.uri,
                    provenance=provenance,
                    attachments=[attachment],
                    evidence=[payload.reference],
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
