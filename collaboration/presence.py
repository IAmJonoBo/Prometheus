"""Presence broadcasting stubs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PresenceEvent:
    """Represents a user's presence heartbeat."""

    user_id: str
    document_id: str
    status: str
    timestamp: datetime


class PresenceService:
    """In-memory presence tracker placeholder."""

    async def broadcast(self, event: PresenceEvent) -> None:
        raise NotImplementedError(
            "Publish presence updates via Redis, NATS, or WebSocket."
        )
