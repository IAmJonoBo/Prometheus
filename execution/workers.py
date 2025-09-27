"""Temporal worker scaffolding for execution pipelines."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "TemporalWorkerConfig",
    "TemporalWorkerMetrics",
    "TemporalWorkerPlan",
    "build_temporal_worker_plan",
]


@dataclass(slots=True)
class TemporalWorkerMetrics:
    """Telemetry endpoints exposed by the Temporal worker."""

    prometheus_port: int | None = None
    otlp_endpoint: str | None = None
    dashboard_links: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TemporalWorkerConfig:
    """Configuration describing how the worker should connect and emit metrics."""

    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "prometheus-pipeline"
    workflows: Sequence[str] = field(default_factory=tuple)
    activities: Mapping[str, str] | None = None
    metrics: TemporalWorkerMetrics = field(default_factory=TemporalWorkerMetrics)


@dataclass(slots=True)
class TemporalWorkerPlan:
    """Result of planning a Temporal worker bootstrap."""

    ready: bool
    connection: dict[str, str]
    instrumentation: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    def describe(self) -> str:
        """Generate a concise status description for logging."""

        status = "ready" if self.ready else "disabled"
        dashboards = ", ".join(self.instrumentation.get("dashboards", [])) or "none"
        return (
            f"Temporal worker {status} for {self.connection['namespace']}"
            f"/{self.connection['task_queue']} (dashboards: {dashboards})"
        )


def _module_available(module: str) -> bool:
    """Return ``True`` when the given module can be imported."""

    return importlib.util.find_spec(module) is not None


def build_temporal_worker_plan(config: TemporalWorkerConfig) -> TemporalWorkerPlan:
    """Create a bootstrap plan describing the Temporal worker deployment."""

    notes: list[str] = []
    ready = True
    if not _module_available("temporalio.worker"):
        ready = False
        notes.append("temporalio is not installed; worker scaffolding only.")
    else:
        notes.append(
            "Temporal worker dependencies resolved; ready to start when configured."
        )

    instrumentation = {
        "prometheus_port": config.metrics.prometheus_port,
        "otlp_endpoint": config.metrics.otlp_endpoint,
        "dashboards": list(config.metrics.dashboard_links),
        "workflows": tuple(config.workflows),
        "activities": tuple(sorted((config.activities or {}).keys())),
    }

    connection = {
        "host": config.host,
        "namespace": config.namespace,
        "task_queue": config.task_queue,
    }

    return TemporalWorkerPlan(
        ready=ready,
        connection=connection,
        instrumentation=instrumentation,
        notes=notes,
    )
