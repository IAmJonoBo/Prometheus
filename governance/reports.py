"""Reporting helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GovernanceReport:
    """Represents a governance summary for dashboards or exports."""

    name: str
    description: str
    data: dict[str, float]


class GovernanceReporter:
    """Bridge to Grafana or downstream BI tooling."""

    async def build_report(self, template: str) -> GovernanceReport:
        raise NotImplementedError("Compile metrics into a structured report.")
