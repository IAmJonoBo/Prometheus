"""Monitoring feedback surface."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from common.contracts import (
    DecisionRecorded,
    EventMeta,
    MetricSample,
    MonitoringSignal,
)


@dataclass(slots=True, kw_only=True)
class MonitoringConfig:
    """Configuration for monitoring pipelines."""

    sample_rate: float = 1.0
    collectors: list[dict[str, Any]] | None = None


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

    def build_signal(
        self, decision: DecisionRecorded, meta: EventMeta
    ) -> MonitoringSignal:
        """Create a monitoring signal summarising the decision outcome."""

        raw_count = decision.policy_checks.get("insight_count", "0")
        try:
            count = float(int(raw_count))
        except ValueError:
            count = 0.0
        metric = MetricSample(
            name="decision.insight_count",
            value=count,
            labels={"status": decision.status},
        )
        return MonitoringSignal(
            meta=meta,
            signal_type="decision",
            description="Decision evaluation completed",
            metrics=[metric],
            incidents=[],
        )

    def emit(self, signal: MonitoringSignal) -> None:
        """Emit a monitoring signal."""

        for collector in self._collectors:
            collector.publish(signal)
