"""Lineage emitter placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LineageEvent:
    """Represents a simplified OpenLineage event payload."""

    job_name: str
    run_id: str
    inputs: list[str]
    outputs: list[str]
    facets: dict[str, str]


class LineageEmitter(Protocol):
    """Interface for emitting lineage events."""

    async def emit(self, event: LineageEvent) -> None: ...


class OpenLineageEmitter:
    """Stub for an OpenLineage HTTP emitter."""

    async def emit(self, event: LineageEvent) -> None:
        raise NotImplementedError("Send the event to your OpenLineage backend.")
