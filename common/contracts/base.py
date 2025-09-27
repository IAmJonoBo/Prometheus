"""Common dataclasses for pipeline event contracts.

These placeholders keep the event traceability expectations from
``docs/architecture.md`` and ``docs/quality-gates.md`` visible in code. They
will evolve into pydantic or protobuf models once implementation starts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True, kw_only=True)
class EvidenceReference:
    """Link to a supporting artefact captured during processing."""

    source_id: str
    uri: str
    description: str | None = None


@dataclass(slots=True, kw_only=True)
class EventMeta:
    """Envelope metadata that every Prometheus event carries."""

    event_id: str
    correlation_id: str
    occurred_at: datetime
    schema_version: str = "1.0.0"
    actor: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class BaseEvent:
    """Base class for all pipeline events."""

    meta: EventMeta
    evidence: list[EvidenceReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the event to a dictionary for logging or transport."""

        return {
            "meta": {
                "event_id": self.meta.event_id,
                "correlation_id": self.meta.correlation_id,
                "occurred_at": self.meta.occurred_at.isoformat(),
                "schema_version": self.meta.schema_version,
                "actor": self.meta.actor,
                "attributes": self.meta.attributes,
            },
            "evidence": [
                {
                    "source_id": ref.source_id,
                    "uri": ref.uri,
                    "description": ref.description,
                }
                for ref in self.evidence
            ],
        }
