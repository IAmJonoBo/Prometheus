"""Primary orchestration surface for the ingestion stage."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.contracts import AttachmentManifest, IngestionNormalised, MetricSample
from common.events import EventFactory

from .connectors import SourceConnector, build_connector
from .models import IngestionPayload
from .persistence import DocumentStore, InMemoryDocumentStore, SQLiteDocumentStore
from .pii import PIIRedactor, RedactionResult
from .scheduler import IngestionScheduler, SchedulerMetrics


@dataclass(slots=True, kw_only=True)
class RedactionMetrics:
    """Telemetry describing PII masking behaviour."""

    documents_redacted: int = 0
    entities_detected: int = 0


@dataclass(slots=True, kw_only=True)
class IngestionRunMetrics:
    """Aggregate ingestion metrics for a pipeline invocation."""

    scheduler: SchedulerMetrics
    payloads_total: int
    redaction: RedactionMetrics

    def to_metric_samples(self) -> list[MetricSample]:
        """Convert the metrics into monitoring samples."""

        samples = [
            MetricSample(
                name="ingestion.connectors.total",
                value=float(self.scheduler.connectors_total),
            ),
            MetricSample(
                name="ingestion.connectors.succeeded",
                value=float(self.scheduler.connectors_succeeded),
            ),
            MetricSample(
                name="ingestion.connectors.failed",
                value=float(self.scheduler.connectors_failed),
            ),
            MetricSample(
                name="ingestion.scheduler.attempts",
                value=float(self.scheduler.attempts),
            ),
            MetricSample(
                name="ingestion.scheduler.retries",
                value=float(self.scheduler.retries),
            ),
            MetricSample(
                name="ingestion.payloads.total",
                value=float(self.payloads_total),
            ),
            MetricSample(
                name="ingestion.redaction.documents",
                value=float(self.redaction.documents_redacted),
            ),
            MetricSample(
                name="ingestion.redaction.entities",
                value=float(self.redaction.entities_detected),
            ),
        ]
        return samples


@dataclass(slots=True, kw_only=True)
class IngestionConfig:
    """Minimal configuration contract for ingestion services."""

    sources: list[dict[str, Any]]
    persistence: dict[str, Any] | None = None
    scheduler: SchedulerConfig | dict[str, Any] | None = None
    redaction: RedactionConfig | dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError("Ingestion requires at least one source definition")
        normalised_sources: list[dict[str, Any]] = []
        for source in self.sources:
            if not isinstance(source, dict):
                raise TypeError("Each source must be a mapping with a 'type' field")
            if "type" not in source:
                raise ValueError("Source definitions must include a 'type'")
            normalised_sources.append(dict(source))
        object.__setattr__(self, "sources", normalised_sources)
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

    def __post_init__(self) -> None:
        if self.concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if self.rate_limit_per_second is not None and self.rate_limit_per_second <= 0:
            raise ValueError("rate_limit_per_second must be positive when set")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("backoff intervals must be non-negative")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= initial_backoff_seconds")
        if self.jitter_seconds < 0:
            raise ValueError("jitter_seconds must be non-negative")


@dataclass(slots=True, kw_only=True)
class RedactionConfig:
    """Configuration for the PII redaction pipeline."""

    enabled: bool = True
    language: str = "en"
    placeholder: str = "[REDACTED]"

    def __post_init__(self) -> None:
        if self.enabled and not self.placeholder:
            raise ValueError("placeholder must be non-empty when redaction is enabled")


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
        scheduler_config = config.scheduler
        if not isinstance(scheduler_config, SchedulerConfig):  # pragma: no cover - defensive guard
            raise TypeError("scheduler configuration must be a SchedulerConfig instance")
        self._scheduler_config = scheduler_config
        self._connectors = list(connectors) if connectors else self._build_connectors()
        self._store = store or self._build_store()
        redaction_config = config.redaction
        if not isinstance(redaction_config, RedactionConfig):  # pragma: no cover - defensive guard
            raise TypeError("redaction configuration must be a RedactionConfig instance")
        self._redactor = redactor or PIIRedactor(
            enabled=redaction_config.enabled,
            language=redaction_config.language,
            placeholder=redaction_config.placeholder,
        )
        self._last_scheduler_metrics: SchedulerMetrics | None = None
        self._last_payloads: int = 0
        self._last_redaction_metrics = RedactionMetrics()

    @property
    def connectors(self) -> Sequence[SourceConnector]:
        """Return the configured connectors for inspection/testing."""

        return self._connectors

    @property
    def metrics(self) -> IngestionRunMetrics | None:
        """Return metrics for the most recent ingestion run, if available."""

        if self._last_scheduler_metrics is None:
            return None
        scheduler = self._last_scheduler_metrics
        redaction = self._last_redaction_metrics
        return IngestionRunMetrics(
            scheduler=SchedulerMetrics(
                connectors_total=scheduler.connectors_total,
                connectors_succeeded=scheduler.connectors_succeeded,
                connectors_failed=scheduler.connectors_failed,
                attempts=scheduler.attempts,
                retries=scheduler.retries,
            ),
            payloads_total=self._last_payloads,
            redaction=RedactionMetrics(
                documents_redacted=redaction.documents_redacted,
                entities_detected=redaction.entities_detected,
            ),
        )

    def collect(self) -> list[IngestionPayload]:
        """Gather raw payloads from configured sources."""

        return asyncio.run(self.collect_async())

    async def collect_async(self) -> list[IngestionPayload]:
        """Asynchronously gather payloads from configured connectors."""

        scheduler = IngestionScheduler(
            self._connectors,
            concurrency=self._scheduler_config.concurrency,
            max_retries=self._scheduler_config.max_retries,
            initial_backoff=self._scheduler_config.initial_backoff_seconds,
            max_backoff=self._scheduler_config.max_backoff_seconds,
            jitter=self._scheduler_config.jitter_seconds,
            rate_limit_per_second=self._scheduler_config.rate_limit_per_second,
        )
        payloads: list[IngestionPayload] = []
        try:
            payloads = await scheduler.run()
            return payloads
        finally:
            self._last_scheduler_metrics = scheduler.metrics
            self._last_payloads = len(payloads)

    def normalise(
        self,
        payloads: Iterable[IngestionPayload],
        factory: EventFactory,
    ) -> list[IngestionNormalised]:
        """Convert raw references into structured documents."""

        normalised: list[IngestionNormalised] = []
        documents_redacted = 0
        entities_detected = 0
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
            if redacted.findings:
                documents_redacted += 1
                entities_detected += len(redacted.findings)
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
        self._last_redaction_metrics = RedactionMetrics(
            documents_redacted=documents_redacted,
            entities_detected=entities_detected,
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
