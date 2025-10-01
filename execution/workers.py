"""Temporal worker scaffolding for execution pipelines."""

from __future__ import annotations

import importlib
import importlib.util
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

__all__ = [
    "TemporalWorkerConfig",
    "TemporalWorkerMetrics",
    "TemporalWorkerPlan",
    "TemporalWorkerRuntime",
    "TemporalValidationReport",
    "ValidationCheck",
    "build_temporal_worker_plan",
    "create_temporal_worker_runtime",
    "validate_temporal_worker_plan",
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


@dataclass(slots=True)
class TemporalWorkerRuntime:
    """Runtime helper that boots a Temporal worker when dependencies exist."""

    plan: TemporalWorkerPlan
    workflows: tuple[Any, ...]
    activities: dict[str, Any]

    async def start(self) -> None:
        """Start the Temporal worker using the computed plan."""

        client_mod = _load_module("temporalio.client")
        worker_mod = _load_module("temporalio.worker")
        if (
            client_mod is None or worker_mod is None
        ):  # pragma: no cover - optional dep guard
            raise RuntimeError(
                "temporalio is required to start the worker; install the optional "
                "dependency and retry"
            )

        instrumentation = _TelemetryBootstrap(self.plan.instrumentation)
        await instrumentation.__aenter__()
        try:
            client = await client_mod.Client.connect(
                self.plan.connection["host"],
                namespace=self.plan.connection["namespace"],
            )
            worker = worker_mod.Worker(
                client,
                task_queue=self.plan.connection["task_queue"],
                workflows=list(self.workflows),
                activities=list(self.activities.values()),
            )
            async with worker:  # pragma: no cover - network interaction
                await worker.run()
        finally:
            await instrumentation.__aexit__(None, None, None)


@dataclass(slots=True)
class ValidationCheck:
    """Connectivity check result for a Temporal worker dependency."""

    label: str
    target: str
    status: bool
    detail: str | None = None
    required: bool = True


@dataclass(slots=True)
class TemporalValidationReport:
    """Aggregate report describing Temporal worker validation results."""

    plan: TemporalWorkerPlan
    checks: tuple[ValidationCheck, ...]
    dashboards: dict[str, bool]

    @property
    def is_ready(self) -> bool:
        """Return ``True`` when the worker plan and required checks succeed."""

        if not self.plan.ready:
            return False
        return all(check.status for check in self.checks if check.required)


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


def create_temporal_worker_runtime(
    config: TemporalWorkerConfig,
) -> TemporalWorkerRuntime | None:
    """Return a runtime helper when the worker should be bootstrapped."""

    plan = build_temporal_worker_plan(config)
    if not plan.ready:
        return None
    workflows = tuple(
        _resolve_symbol(ref)
        for ref in _normalise_references(config.workflows, _DEFAULT_WORKFLOWS)
    )
    activities = {
        name: _resolve_symbol(ref)
        for name, ref in _normalise_activity_refs(config.activities).items()
    }
    return TemporalWorkerRuntime(plan=plan, workflows=workflows, activities=activities)


def validate_temporal_worker_plan(
    config: TemporalWorkerConfig,
    *,
    known_dashboards: Sequence[Any] | None = None,
    timeout: float = 2.0,
) -> TemporalValidationReport:
    """Validate connectivity implied by the Temporal worker configuration."""

    plan = build_temporal_worker_plan(config)
    checks = _collect_validation_checks(plan, timeout)
    dashboards = _dashboard_status(plan.instrumentation, known_dashboards)
    return TemporalValidationReport(plan=plan, checks=checks, dashboards=dashboards)


def _collect_validation_checks(
    plan: TemporalWorkerPlan, timeout: float
) -> tuple[ValidationCheck, ...]:
    checks: list[ValidationCheck] = []
    connection = plan.connection.get("host", "")
    if connection:
        checks.append(
            ValidationCheck(
                label="Temporal gRPC",
                target=connection,
                status=_probe_endpoint(connection, timeout=timeout),
                detail=None if plan.ready else "temporalio dependency missing",
            )
        )

    instrumentation = plan.instrumentation
    prom_port = instrumentation.get("prometheus_port")
    if prom_port:
        target = f"localhost:{int(prom_port)}"
        checks.append(
            ValidationCheck(
                label="Prometheus metrics",
                target=target,
                status=_probe_endpoint(target, timeout=timeout),
                required=False,
            )
        )

    otlp_endpoint = instrumentation.get("otlp_endpoint")
    if otlp_endpoint:
        otlp_target = _normalise_grpc_target(str(otlp_endpoint))
        checks.append(
            ValidationCheck(
                label="OTLP collector",
                target=otlp_target,
                status=_probe_endpoint(otlp_target, timeout=timeout),
                required=False,
            )
        )

    return tuple(checks)


def _dashboard_status(
    instrumentation: Mapping[str, Any],
    known_dashboards: Sequence[Any] | None,
) -> dict[str, bool]:
    dashboards: dict[str, bool] = {}
    known: set[str] = set()
    if known_dashboards:
        for entry in known_dashboards:
            if isinstance(entry, str):
                known.add(entry)
            else:
                uid = getattr(entry, "uid", None)
                if uid:
                    known.add(f"grafana://{uid}")
    for link in instrumentation.get("dashboards", []):
        dashboards[link] = link in known if known else True
    return dashboards


def _normalise_references(
    references: Sequence[str],
    defaults: dict[str, str],
) -> tuple[str, ...]:
    if not references:
        return tuple(defaults[key] for key in sorted(defaults))
    normalised: list[str] = []
    for ref in references:
        normalised.append(defaults.get(ref, ref))
    return tuple(normalised)


def _normalise_activity_refs(
    activities: Mapping[str, str] | None,
) -> Mapping[str, str]:
    if not activities:
        return dict(_DEFAULT_ACTIVITIES)
    payload: dict[str, str] = {}
    for name, ref in activities.items():
        payload[name] = _DEFAULT_ACTIVITIES.get(name, ref)
    return payload


def _resolve_symbol(reference: str) -> Any:
    module_name, separator, target = reference.partition(":")
    if not separator:
        raise ValueError(
            "Worker references must be in 'module:attribute' form; "
            f"received '{reference}'"
        )
    module = importlib.import_module(module_name)
    attribute: Any = module
    for part in target.split("."):
        attribute = getattr(attribute, part)
    return attribute


def _load_module(module: str) -> Any | None:
    try:  # pragma: no cover - optional dependency detection
        return importlib.import_module(module)
    except ImportError:
        return None


def _probe_endpoint(endpoint: str, *, timeout: float = 2.0) -> bool:
    """Return ``True`` when a TCP connection to the endpoint succeeds."""

    target = endpoint.strip()
    if not target:
        return True

    host: str | None
    port: int | None
    scheme = ""
    if "://" in target:
        parsed = urlparse(target)
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme
    else:
        parsed = urlparse(f"//{target}")
        host = parsed.hostname
        port = parsed.port

    if host is None:
        return True

    if port is None:
        if scheme == "https":
            port = 443
        elif scheme in {"grpc", "grpcs"}:
            port = 4317 if scheme == "grpc" else 4318
        else:
            port = 80

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _normalise_grpc_target(endpoint: str) -> str:
    target = endpoint.strip()
    if not target:
        return ""
    if "://" not in target:
        return target
    parsed = urlparse(target)
    host = parsed.hostname or "localhost"
    port = parsed.port
    if port is None:
        port = 4317 if parsed.scheme == "grpc" else 4318
    return f"{host}:{port}"


class _TelemetryBootstrap:
    """Context manager that configures Prometheus and OTLP exporters."""

    def __init__(self, instrumentation: Mapping[str, Any]) -> None:
        self._instrumentation = instrumentation
        self._prometheus_started = False
        self._meter_provider = None

    async def __aenter__(self) -> _TelemetryBootstrap:
        self._start_prometheus()
        self._configure_otlp()
        return self

    async def __aexit__(
        self, exc_type, exc, tb
    ) -> None:  # noqa: ANN001, D401 - async context API
        self._shutdown_otlp()

    def _start_prometheus(self) -> None:
        port = self._instrumentation.get("prometheus_port")
        if not port:
            return
        try:
            prometheus_client = importlib.import_module("prometheus_client")
        except ImportError:  # pragma: no cover - optional dependency guard
            return
        start_http_server = getattr(prometheus_client, "start_http_server", None)
        if start_http_server is None:  # pragma: no cover - optional dependency guard
            return
        if not self._prometheus_started:
            start_http_server(int(port))
            self._prometheus_started = True

    def _configure_otlp(self) -> None:
        endpoint = self._instrumentation.get("otlp_endpoint")
        if not endpoint:
            return
        try:
            exporter_mod = importlib.import_module(
                "opentelemetry.exporter.otlp.proto.grpc.metric_exporter"
            )
            sdk_metrics = importlib.import_module("opentelemetry.sdk.metrics")
            sdk_export = importlib.import_module("opentelemetry.sdk.metrics.export")
            resources_mod = importlib.import_module("opentelemetry.sdk.resources")
        except ImportError:  # pragma: no cover - optional dependency guard
            return
        otlp_metric_exporter_cls = getattr(exporter_mod, "OTLPMetricExporter", None)
        meter_provider_cls = getattr(sdk_metrics, "MeterProvider", None)
        metric_reader_cls = getattr(sdk_export, "PeriodicExportingMetricReader", None)
        resource_cls = getattr(resources_mod, "Resource", None)
        if None in (
            otlp_metric_exporter_cls,
            meter_provider_cls,
            metric_reader_cls,
            resource_cls,
        ):  # pragma: no cover - optional dependency guard
            return
        assert otlp_metric_exporter_cls is not None
        assert meter_provider_cls is not None
        assert metric_reader_cls is not None
        assert resource_cls is not None
        resource = resource_cls.create({"service.name": "prometheus-temporal-worker"})
        exporter = otlp_metric_exporter_cls(endpoint=endpoint, insecure=True)
        reader = metric_reader_cls(exporter)
        self._meter_provider = meter_provider_cls(
            resource=resource, metric_readers=[reader]
        )
        try:
            metrics_mod = importlib.import_module("opentelemetry.metrics")
        except ImportError:  # pragma: no cover - optional dependency guard
            return
        set_meter_provider = getattr(metrics_mod, "set_meter_provider", None)
        if set_meter_provider is None:  # pragma: no cover - optional dependency guard
            return
        set_meter_provider(self._meter_provider)

    def _shutdown_otlp(self) -> None:
        provider = self._meter_provider
        if provider is None:
            return
        provider.shutdown()
        self._meter_provider = None


_DEFAULT_WORKFLOWS: dict[str, str] = {
    "PrometheusPipeline": "execution.workflows:PrometheusPipelineWorkflow",
}

_DEFAULT_ACTIVITIES: dict[str, str] = {
    "record_decision": "execution.workflows:record_decision_activity",
    "emit_metrics": "execution.workflows:emit_metrics_activity",
}
