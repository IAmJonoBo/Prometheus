"""Plugin scaffolding for Prometheus."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from common.contracts import BaseEvent
from common.events import EventBus


class PipelinePlugin(Protocol):
    """Interface for pipeline plugins."""

    name: str

    def setup(self, bus: EventBus) -> None:
        """Register event handlers on the provided bus."""


@dataclass(slots=True)
class PluginRegistry:
    """Tracks registered plugins and exposes their metadata."""

    bus: EventBus
    _plugins: list[PipelinePlugin] = field(default_factory=list)

    def register(self, plugin: PipelinePlugin) -> None:
        plugin.setup(self.bus)
        self._plugins.append(plugin)

    def names(self) -> Iterable[str]:
        return (plugin.name for plugin in self._plugins)

    def plugins(self) -> Iterable[PipelinePlugin]:
        return tuple(self._plugins)


@dataclass(slots=True)
class AuditTrailPlugin:
    """Captures published events for compliance and debugging."""

    name: str = "audit_trail"
    events: list[BaseEvent] = field(default_factory=list)

    def setup(self, bus: EventBus) -> None:  # pragma: no cover - trivial wiring
        def _record(event: BaseEvent) -> None:
            self.events.append(event)

        bus.subscribe(BaseEvent, _record)


__all__ = ["AuditTrailPlugin", "PipelinePlugin", "PluginRegistry"]

