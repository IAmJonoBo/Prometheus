"""Primary orchestration surface for the ingestion stage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from common.contracts import EvidenceReference, IngestionNormalised


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

        raise NotImplementedError("Ingestion collection has not been implemented")

    def normalise(
        self, links: Iterable[EvidenceReference]
    ) -> Iterable[IngestionNormalised]:
        """Convert raw references into structured documents."""

        _ = list(links)
        # Placeholder: concrete drivers will populate this later on.
        return []
