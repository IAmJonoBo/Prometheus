"""Primary orchestration surface for the ingestion stage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from common.contracts import EvidenceReference, IngestionNormalised
from common.events import EventFactory


@dataclass(slots=True, kw_only=True)
class IngestionConfig:
    """Minimal configuration contract for ingestion services."""

    sources: list[str]


class IngestionService:
    """Normalises raw inputs into shared documents.

    The real implementation will surface async collection, rate limiting, and
    source-specific adapters. For now we just expose a synchronous signature so
    downstream stages can depend on a stable interface while we bootstrap the
    modules.
    """

    def __init__(self, config: IngestionConfig) -> None:
        self._config = config

    def collect(self) -> Iterable[EvidenceReference]:
        """Gather raw references from configured sources."""

        for source in self._config.sources:
            yield EvidenceReference(
                source_id=source,
                uri=source,
                description=f"Configured source {source}",
            )

    def normalise(
        self,
        links: Iterable[EvidenceReference],
        factory: EventFactory,
    ) -> list[IngestionNormalised]:
        """Convert raw references into structured documents."""

        normalised: list[IngestionNormalised] = []
        for link in links:
            meta = factory.create_meta(event_name="ingestion.normalised")
            normalised.append(
                IngestionNormalised(
                    meta=meta,
                    source_system=link.source_id,
                    canonical_uri=link.uri,
                    provenance={"description": link.description or ""},
                    attachments=[],
                )
            )
        return normalised
