"""Monitoring signal collectors that integrate with observability stacks."""
from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from common.contracts import MonitoringSignal

from .service import SignalCollector

try:
    metrics_module = importlib.util.find_spec("opentelemetry.metrics")
except ModuleNotFoundError:  # pragma: no cover - package missing entirely
    metrics_module = None
if metrics_module is not None:  # pragma: no branch - executed when installed
    metrics = cast(Any, importlib.import_module("opentelemetry.metrics"))
    sdk_metrics = cast(Any, importlib.import_module("opentelemetry.sdk.metrics"))
    metrics_export = cast(
        Any, importlib.import_module("opentelemetry.sdk.metrics.export")
    )
    MeterProvider = sdk_metrics.MeterProvider
    ConsoleMetricExporter = metrics_export.ConsoleMetricExporter
    PeriodicExportingMetricReader = metrics_export.PeriodicExportingMetricReader
else:  # pragma: no cover - fallback for environments without opentelemetry
    metrics = None  # type: ignore[assignment]
    MeterProvider = None  # type: ignore[assignment]
    ConsoleMetricExporter = None  # type: ignore[assignment]
    PeriodicExportingMetricReader = None  # type: ignore[assignment]

try:
    prometheus_spec = importlib.util.find_spec("prometheus_client")
except ModuleNotFoundError:  # pragma: no cover - package missing entirely
    prometheus_spec = None
if prometheus_spec is not None:  # pragma: no branch - executed when installed
    prometheus_client = cast(Any, importlib.import_module("prometheus_client"))
    CollectorRegistry = prometheus_client.CollectorRegistry
    Gauge = prometheus_client.Gauge
    push_to_gateway = prometheus_client.push_to_gateway
else:  # pragma: no cover - fallback for environments without prometheus-client

    class CollectorRegistry:  # type: ignore[no-redef]
        def __init__(self) -> None:
            self.metrics: dict[str, float] = {}

    class Gauge:  # type: ignore[no-redef]
        def __init__(
            self,
            name: str,
            documentation: str,
            labelnames: list[str] | None = None,
            registry: CollectorRegistry | None = None,
        ) -> None:
            self.name = name
            self.documentation = documentation
            self.labelnames = labelnames or []
            self.registry = registry or CollectorRegistry()

        def labels(self, **labels: str) -> _GaugeHandle:
            return _GaugeHandle(self, labels)

    class _GaugeHandle:
        def __init__(self, gauge: Gauge, labels: dict[str, str]) -> None:
            self._gauge = gauge
            self._labels = labels

        def set(self, value: float) -> None:
            key = f"{self._gauge.name}:{sorted(self._labels.items())}"
            self._gauge.registry.metrics[key] = value

    def push_to_gateway(gateway: str, job: str, registry: CollectorRegistry) -> None:  # type: ignore[no-redef]
        return


class _NoOpCounter:
    def add(self, value: float, attributes: dict[str, Any] | None = None) -> None:
        return


class _NoOpMeter:
    def create_counter(self, name: str) -> _NoOpCounter:
        return _NoOpCounter()


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
        self._meter: Any
        self._counters: dict[str, Any]
        if metrics is None or MeterProvider is None or PeriodicExportingMetricReader is None:
            self._meter = _NoOpMeter()
            self._counters = {}
            return

        assert metrics is not None
        assert MeterProvider is not None
        assert PeriodicExportingMetricReader is not None
        assert ConsoleMetricExporter is not None

        console_exporter_cls = cast(Any, ConsoleMetricExporter)

        if self.exporter == "console":
            metric_exporter = console_exporter_cls()
        else:  # pragma: no cover - external exporters exercised in integration tests
            exporter_module = cast(
                Any,
                importlib.import_module(
                    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter"
                ),
            )

            metric_exporter = exporter_module.OTLPMetricExporter(
                endpoint=self.exporter
            )
        reader_cls = cast(Any, PeriodicExportingMetricReader)
        provider_cls = cast(Any, MeterProvider)
        metrics_api = cast(Any, metrics)
        reader = reader_cls(
            metric_exporter,
            export_interval_millis=self.interval_ms,
        )
        provider = provider_cls(metric_readers=[reader])
        metrics_api.set_meter_provider(provider)
        self._meter = metrics_api.get_meter("prometheus.monitoring")
        self._counters = {}

    def publish(self, signal: MonitoringSignal) -> None:
        self.signals.append(signal)
        meter = cast(Any, self._meter)
        for metric in signal.metrics:
            counter = self._counters.get(metric.name)
            if counter is None:
                creator = cast(
                    Callable[[str], Any] | None,
                    getattr(meter, "create_counter", None),
                )
                if creator is None:
                    continue
                assert creator is not None
                counter = creator(metric.name)
                self._counters[metric.name] = counter
            cast(Any, counter).add(metric.value, attributes=metric.labels)


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

