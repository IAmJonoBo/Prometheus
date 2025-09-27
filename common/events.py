"""Event system scaffolding for the Prometheus pipeline."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from .contracts import BaseEvent, EventMeta

EventT = TypeVar("EventT", bound=BaseEvent)


@dataclass(slots=True)
class EventFactory:
    """Produce :class:`EventMeta` instances with shared correlation IDs."""

    correlation_id: str
    schema_version: str = "1.0.0"

    def create_meta(
        self,
        *,
        event_name: str,
        actor: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> EventMeta:
        """Return a fresh event envelope for the provided ``event_name``."""

        attrs: dict[str, Any] = {"event_name": event_name}
        if attributes:
            attrs.update(attributes)
        return EventMeta(
            event_id=self._uuid(),
            correlation_id=self.correlation_id,
            occurred_at=datetime.now(UTC),
            schema_version=self.schema_version,
            actor=actor,
            attributes=attrs,
        )

    @staticmethod
    def _uuid() -> str:
        from uuid import uuid4

        return str(uuid4())


class EventBus:
    """Synchronous pub/sub broker used while bootstrapping the pipeline."""

    def __init__(self) -> None:
        self._subscribers: MutableMapping[
            type[BaseEvent], list[Callable[[BaseEvent], None]]
        ] = defaultdict(list)
        self._history: list[BaseEvent] = []

    def subscribe(
        self, event_type: type[EventT], handler: Callable[[EventT], None]
    ) -> None:
        """Register ``handler`` for the given ``event_type``."""

        def _wrapper(event: BaseEvent) -> None:
            handler(event)  # type: ignore[arg-type]

        self._subscribers[event_type].append(_wrapper)

    def publish(self, event: EventT) -> None:
        """Dispatch ``event`` to matching subscribers and record history."""

        self._history.append(event)
        for registered_type, handlers in list(self._subscribers.items()):
            if isinstance(event, registered_type):
                for handler in handlers:
                    handler(event)

    def replay(self) -> Iterable[BaseEvent]:
        """Return an iterator over all published events."""

        return iter(self._history)


__all__ = ["EventBus", "EventFactory"]

