"""Governance-related event contracts for CI automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class CIFailureRaised(BaseEvent):
    """Event emitted when CI detects an actionable dry-run failure."""

    shard: str
    run_id: str
    query: str
    severity: str = "warning"
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload.update(
            {
                "shard": self.shard,
                "run_id": self.run_id,
                "query": self.query,
                "severity": self.severity,
                "warnings": list(self.warnings),
                "details": self.details,
            }
        )
        return payload


__all__ = ["CIFailureRaised"]
