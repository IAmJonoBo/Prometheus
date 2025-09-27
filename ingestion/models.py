"""Dataclasses shared across ingestion components."""

from __future__ import annotations

from dataclasses import dataclass, field

from common.contracts import EvidenceReference


@dataclass(slots=True, kw_only=True)
class IngestionPayload:
    """Container for raw content fetched from a source connector."""

    reference: EvidenceReference
    content: str
    metadata: dict[str, str] = field(default_factory=dict)

