"""Audit ledger primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class AuditEntry:
    """Immutable log entry describing a decision and its justification."""

    entry_id: str
    actor: str
    action: str
    resource: str
    timestamp: datetime
    details: dict[str, str]


class AuditLedger:
    """Abstracts storage of audit entries."""

    async def append(self, entry: AuditEntry) -> None:
        raise NotImplementedError(
            "Persist the audit entry to Postgres or an append-only log."
        )

    async def query(self, *, resource: str | None = None) -> Iterable[AuditEntry]:
        raise NotImplementedError("Return a filtered view of the audit history.")
