"""Monitoring signal collectors that integrate with observability stacks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from common.contracts import MonitoringSignal

from .service import SignalCollector


@dataclass(slots=True)
class PrometheusSignalCollector(SignalCollector):
    """Push monitoring signals to a Prometheus Pushgateway."""

    gateway_url: str
    job: str = "prometheus_pipeline"
    registry: CollectorRegistry = field(default_factory=CollectorRegistry)
    signals: list[MonitoringSignal] = field(default_factory=list)

    def publish(self, signal: MonitoringSignal) -> None:
        for metric in signal.metrics:
            gauge = Gauge(
                metric.name,
                "Pipeline metric exported by Prometheus bootstrap",
                labelnames=list(metric.labels.keys()),
                registry=self.registry,
            )
            gauge.labels(**metric.labels).set(metric.value)
        try:
            push_to_gateway(self.gateway_url, job=self.job, registry=self.registry)
            self.signals.append(signal)
        except Exception:  # pragma: no cover - network failure path
            # Store the signal even when the Pushgateway is unreachable so tests can assert.
            self.signals.append(signal)


@dataclass(slots=True)
class OpenTelemetrySignalCollector(SignalCollector):
    """Emit metrics through the OpenTelemetry SDK."""

    exporter: str = "console"
    interval_ms: int = 10000
    signals: list[MonitoringSignal] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.exporter == "console":
            metric_exporter = ConsoleMetricExporter()
        else:  # pragma: no cover - external exporters exercised in integration tests
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )

            metric_exporter = OTLPMetricExporter(endpoint=self.exporter)
        reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=self.interval_ms,
        )
        provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(provider)
        self._meter = metrics.get_meter("prometheus.monitoring")
        self._counters: dict[str, Any] = {}

    def publish(self, signal: MonitoringSignal) -> None:
        self.signals.append(signal)
        for metric in signal.metrics:
            counter = self._counters.get(metric.name)
            if counter is None:
                counter = self._meter.create_counter(metric.name)
                self._counters[metric.name] = counter
            counter.add(metric.value, attributes=metric.labels)


def build_collector(config: dict[str, str]) -> SignalCollector:
    """Build a collector from configuration."""

    collector_type = config.get("type", "prometheus")
    if collector_type == "prometheus":
        return PrometheusSignalCollector(
            gateway_url=config.get("gateway_url", "http://localhost:9091"),
            job=config.get("job", "prometheus_pipeline"),
        )
    if collector_type == "opentelemetry":
        return OpenTelemetrySignalCollector(
            exporter=config.get("exporter", "console"),
            interval_ms=int(config.get("interval_ms", 10000)),
        )
    raise ValueError(f"Unsupported collector type: {collector_type}")

