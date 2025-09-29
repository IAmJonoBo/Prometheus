"""CRDT placeholders for collaborative editing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class CRDTUpdate:
    """Represents a Yjs update payload."""

    document_id: str
    payload: bytes


@dataclass(slots=True)
class CRDTDocument:
    """Metadata for a collaborative document."""

    document_id: str
    snapshot: bytes | None = None


class CRDTGateway(Protocol):
    """Gateway that applies CRDT updates."""

    async def apply_update(
        self, document: CRDTDocument, update: CRDTUpdate
    ) -> CRDTDocument: ...


class YjsGateway:
    """Placeholder Yjs gateway implementation."""

    async def apply_update(
        self, document: CRDTDocument, update: CRDTUpdate
    ) -> CRDTDocument:
        raise NotImplementedError("Integrate with y-py or y-websocket server.")
