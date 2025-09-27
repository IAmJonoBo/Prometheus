"""Monitoring stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class MetricSample:
    """Structured metric observation captured by monitoring."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class MonitoringSignal(BaseEvent):
    """Feedback signal emitted back into the adaptation loop."""

    signal_type: str
    description: str
    metrics: list[MetricSample] = field(default_factory=list)
    incidents: list[str] = field(default_factory=list)
