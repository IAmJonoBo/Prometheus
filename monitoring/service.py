"""Monitoring feedback surface."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from common.contracts import EventMeta, MonitoringSignal


@dataclass(slots=True, kw_only=True)
class MonitoringConfig:
    """Configuration for monitoring pipelines."""

    sample_rate: float = 1.0


class SignalCollector:
    """Interface for downstream signal sinks."""

    def publish(self, signal: MonitoringSignal) -> None:
        """Publish a monitoring signal."""

        raise NotImplementedError


class MonitoringService:
    """Distributes monitoring signals to configured sinks."""

    def __init__(
        self, config: MonitoringConfig, collectors: Iterable[SignalCollector]
    ) -> None:
        self._config = config
        self._collectors = list(collectors)

    def emit(self, signal: MonitoringSignal, meta: EventMeta) -> None:
        """Emit a monitoring signal."""

        _ = meta
        for collector in self._collectors:
            collector.publish(signal)
