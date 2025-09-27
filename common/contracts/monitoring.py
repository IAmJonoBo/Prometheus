"""Monitoring stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class MetricSample:
    """Structured metric observation captured by monitoring."""

    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class MonitoringSignal(BaseEvent):
    """Feedback signal emitted back into the adaptation loop."""

    signal_type: str
    description: str
    metrics: List[MetricSample] = field(default_factory=list)
    incidents: List[str] = field(default_factory=list)
