"""Pipeline orchestration for Prometheus."""

from __future__ import annotations

import logging
import socket
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from common.contracts import (
    DecisionRecorded,
    ExecutionPlanDispatched,
    IngestionNormalised,
    MetricSample,
    MonitoringSignal,
    ReasoningAnalysisProposed,
    RetrievalContextBundle,
)
from common.events import EventBus, EventFactory
from decision.service import DecisionService
from execution.adapters import TemporalExecutionAdapter, WebhookExecutionAdapter
from execution.service import ExecutionAdapter, ExecutionConfig, ExecutionService
from execution.workers import (
    TemporalWorkerConfig as WorkerConfig,
)
from execution.workers import (
    TemporalWorkerMetrics,
    TemporalWorkerPlan,
    TemporalWorkerRuntime,
    build_temporal_worker_plan,
    create_temporal_worker_runtime,
)
from ingestion.service import IngestionService
from monitoring.collectors import build_collector
from monitoring.dashboards import GrafanaDashboard, build_default_dashboards
from monitoring.service import MonitoringConfig, MonitoringService, SignalCollector
from reasoning.service import ReasoningService
from retrieval.service import (
    InMemoryRetriever,
    RetrievalService,
    build_hybrid_retriever,
)

from .config import PrometheusConfig
from .plugins import AuditTrailPlugin, PipelinePlugin, PluginRegistry

logger = logging.getLogger(__name__)

_DEFAULT_OPENSEARCH_HOST = "http://localhost:9200"
_DEFAULT_QDRANT_URL = "http://localhost:6333"
_DEFAULT_TEMPORAL_HOST = "localhost:7233"


@dataclass(slots=True)
class PipelineResult:
    """Structured result of a pipeline execution."""

    ingestion: list[IngestionNormalised]
    retrieval: RetrievalContextBundle
    reasoning: ReasoningAnalysisProposed
    decision: DecisionRecorded
    execution: ExecutionPlanDispatched
    monitoring: MonitoringSignal


class PrometheusOrchestrator:
    """Coordinates the pipeline stages for a single run."""

    def __init__(
        self,
        config: PrometheusConfig,
        *,
        bus: EventBus,
        ingestion: IngestionService,
        retrieval: RetrievalService,
        reasoning: ReasoningService,
        decision: DecisionService,
        execution: ExecutionService,
        monitoring: MonitoringService,
        plugins: Iterable[PipelinePlugin] | None = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._ingestion = ingestion
        self._retrieval = retrieval
        self._reasoning = reasoning
        self._decision = decision
        self._execution = execution
        self._monitoring = monitoring
        self.registry = PluginRegistry(bus)
        self.bus = bus
        self.execution_adapter: ExecutionAdapter | None = None
        self.signal_collectors: list[SignalCollector] = []
        self.worker_plan: TemporalWorkerPlan | None = None
        self.worker_runtime: TemporalWorkerRuntime | None = None
        self.dashboards: list[GrafanaDashboard] = []
        for plugin in plugins or ():
            self.registry.register(plugin)

    def run(self, query: str, *, actor: str | None = None) -> PipelineResult:
        """Execute the end-to-end pipeline for a query."""

        factory = EventFactory(correlation_id=self._new_correlation())
        payloads = list(self._ingestion.collect())
        normalised = self._ingestion.normalise(payloads, factory)
        for event in normalised:
            self._bus.publish(event)

        ingestion_metrics = self._ingestion.metrics
        extra_metrics: list[MetricSample] = []
        if ingestion_metrics is not None:
            extra_metrics.extend(ingestion_metrics.to_metric_samples())

        self._retrieval.ingest(normalised)
        retrieval_meta = factory.create_meta(
            event_name="retrieval.context", actor=actor
        )
        context = self._retrieval.build_context(query, retrieval_meta)
        self._bus.publish(context)

        reasoning_meta = factory.create_meta(
            event_name="reasoning.analysis", actor=actor
        )
        analysis = self._reasoning.analyse(context, reasoning_meta)
        self._bus.publish(analysis)

        decision_meta = factory.create_meta(
            event_name="decision.recorded", actor=actor
        )
        decision = self._decision.evaluate(analysis, decision_meta)
        self._bus.publish(decision)

        execution_meta = factory.create_meta(
            event_name="execution.dispatched", actor=actor
        )
        execution_plan = self._execution.sync(decision, execution_meta)
        self._bus.publish(execution_plan)

        monitoring_meta = factory.create_meta(
            event_name="monitoring.signal", actor=actor
        )
        signal = self._monitoring.build_signal(
            decision,
            monitoring_meta,
            extra_metrics=extra_metrics,
        )
        self._monitoring.emit(signal)
        self._bus.publish(signal)

        return PipelineResult(
            ingestion=normalised,
            retrieval=context,
            reasoning=analysis,
            decision=decision,
            execution=execution_plan,
            monitoring=signal,
        )

    def _new_correlation(self) -> str:
        from uuid import uuid4

        return str(uuid4())


def build_orchestrator(config: PrometheusConfig) -> PrometheusOrchestrator:
    """Create a default orchestrator wired with in-memory adapters."""

    _verify_external_dependencies(config)
    bus = EventBus()
    ingestion = IngestionService(config.ingestion)
    if config.retrieval.strategy == "hybrid":
        retriever = build_hybrid_retriever(config.retrieval)
    else:
        retriever = InMemoryRetriever()
    retrieval = RetrievalService(config.retrieval, retriever)
    reasoning = ReasoningService(config.reasoning)
    decision = DecisionService(config.decision)
    execution_adapter = _build_execution_adapter(config.execution)
    execution = ExecutionService(config.execution, execution_adapter)
    collectors = _build_signal_collectors(config.monitoring)
    dashboards = _build_dashboards(config.monitoring)
    worker_plan, worker_runtime = _build_worker_resources(config.execution)
    monitoring = MonitoringService(config.monitoring, collectors)
    orchestrator = PrometheusOrchestrator(
        config,
        bus=bus,
        ingestion=ingestion,
        retrieval=retrieval,
        reasoning=reasoning,
        decision=decision,
        execution=execution,
        monitoring=monitoring,
        plugins=[AuditTrailPlugin()],
    )
    orchestrator.execution_adapter = execution_adapter
    orchestrator.signal_collectors = collectors
    orchestrator.dashboards = dashboards
    orchestrator.worker_plan = worker_plan
    orchestrator.worker_runtime = worker_runtime
    return orchestrator


def _verify_external_dependencies(config: PrometheusConfig) -> None:
    """Emit warnings when optional external services are unreachable."""

    _check_opensearch_dependency(config.retrieval.lexical)
    _check_qdrant_dependency(config.retrieval.vector)
    _check_temporal_dependency(config.execution)
    _check_prometheus_collectors(config.monitoring.collectors)


def _check_opensearch_dependency(lexical: dict[str, object] | None) -> None:
    if not lexical or lexical.get("backend") != "opensearch":
        return
    raw_hosts = lexical.get("hosts")
    hosts: tuple[str, ...]
    if not raw_hosts:
        hosts = (_DEFAULT_OPENSEARCH_HOST,)
    elif isinstance(raw_hosts, (list, tuple, set)):
        hosts = tuple(str(host) for host in raw_hosts)
    else:
        hosts = (str(raw_hosts),)

    for host in hosts:
        if not _probe_endpoint(host):
            _log_dependency_warning(
                "OpenSearch host",
                host,
                "falling back to RapidFuzz lexical search",
            )
            break


def _check_temporal_dependency(execution: ExecutionConfig) -> None:
    if execution.sync_target != "temporal":
        return
    adapter = execution.adapter or {}
    host = str(adapter.get("host", _DEFAULT_TEMPORAL_HOST))
    if host and not _probe_endpoint(host):
        _log_dependency_warning(
            "Temporal host",
            str(host),
            "execution dispatch will use in-memory fallbacks",
        )


def _check_prometheus_collectors(
    collectors: list[dict[str, object]] | None,
) -> None:
    if not collectors:
        return
    for collector_config in collectors:
        if collector_config.get("type") != "prometheus":
            continue
        gateway = collector_config.get("gateway_url")
        if gateway and not _probe_endpoint(str(gateway)):
            _log_dependency_warning(
                "Prometheus Pushgateway",
                str(gateway),
                "metrics push will be skipped",
            )


def _log_dependency_warning(label: str, endpoint: str, action: str) -> None:
    logger.warning("%s %s is unreachable; %s.", label, endpoint, action)


def _check_qdrant_dependency(vector: dict[str, object] | None) -> None:
    if not vector or vector.get("backend") != "qdrant":
        return
    raw_target = vector.get("url") or vector.get("location")
    if raw_target is None:
        raw_target = _DEFAULT_QDRANT_URL
    target = str(raw_target).strip()
    if not target or target.startswith(":memory"):
        return
    if "://" not in target and ":" not in target:
        target = f"{target}:6333"
    if not _probe_endpoint(target):
        _log_dependency_warning(
            "Qdrant endpoint",
            target,
            "vector search will be disabled",
        )


def _probe_endpoint(endpoint: str, *, timeout: float = 1.0) -> bool:
    """Return ``True`` when a TCP connection can be established."""

    host: str | None
    port: int | None
    scheme = ""
    target = endpoint.strip()
    if not target:
        return True

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
        elif scheme == "grpc":
            port = 4317
        elif scheme == "grpcs":
            port = 4318
        else:
            port = 80

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass(slots=True)
class _InMemoryExecutionAdapter(ExecutionAdapter):
    """Execution adapter that records dispatched notes."""

    notes: list[str] = field(default_factory=list)

    def dispatch(self, decision: DecisionRecorded) -> Iterable[str]:
        note = (
            f"Dispatched decision {decision.meta.event_id} to"
            f" {decision.decision_type}"
        )
        self.notes.append(note)
        yield note


@dataclass(slots=True)
class _InMemorySignalCollector(SignalCollector):
    """Collector storing monitoring signals for later inspection."""

    signals: list[MonitoringSignal] = field(default_factory=list)

    def publish(self, signal: MonitoringSignal) -> None:
        self.signals.append(signal)


def _build_execution_adapter(config: ExecutionConfig) -> ExecutionAdapter:
    if config.sync_target == "temporal":
        options = config.adapter or {}
        return TemporalExecutionAdapter(
            target_host=options.get("host", _DEFAULT_TEMPORAL_HOST),
            namespace=options.get("namespace", "default"),
            task_queue=options.get("task_queue", "prometheus-pipeline"),
            workflow=options.get("workflow", "PrometheusPipeline"),
        )
    if config.sync_target == "webhook":
        options = config.adapter or {}
        endpoint = options.get("endpoint")
        if not endpoint:
            raise ValueError("Webhook execution adapter requires an 'endpoint'")
        return WebhookExecutionAdapter(
            endpoint=endpoint,
            headers=options.get("headers", {}),
            timeout=float(options.get("timeout", 10.0)),
        )
    return _InMemoryExecutionAdapter()


def _build_signal_collectors(config: MonitoringConfig) -> list[SignalCollector]:
    collectors: list[SignalCollector] = []
    if config.collectors:
        for collector_config in config.collectors:
            collectors.append(build_collector(collector_config))
    else:
        collectors.append(_InMemorySignalCollector())
    return collectors


def _build_dashboards(config: MonitoringConfig) -> list[GrafanaDashboard]:
    extras: list[GrafanaDashboard] = []
    if config.dashboards:
        for dashboard in config.dashboards:
            extras.append(
                GrafanaDashboard(
                    title=dashboard.get("title", "Custom Dashboard"),
                    uid=dashboard.get("uid", "prom-custom"),
                    slug=dashboard.get("slug", "custom"),
                    panels=list(dashboard.get("panels", [])),
                    tags=dashboard.get(
                        "tags", ["prometheus-os", "observability"]
                    ),
                    description=dashboard.get("description", ""),
                )
            )
    return build_default_dashboards(extras)


def _build_worker_resources(
    config: ExecutionConfig,
) -> tuple[TemporalWorkerPlan | None, TemporalWorkerRuntime | None]:
    if config.sync_target != "temporal":
        return None, None
    worker_config = _build_worker_config(config)
    runtime = create_temporal_worker_runtime(worker_config)
    if runtime is not None:
        return runtime.plan, runtime
    return build_temporal_worker_plan(worker_config), None


def _build_worker_config(config: ExecutionConfig) -> WorkerConfig:
    worker = config.worker or {}
    adapter_options = config.adapter or {}
    metrics_config = worker.get("metrics", {})
    default_workflow = adapter_options.get("workflow", "PrometheusPipeline")
    configured_workflows = worker.get("workflows")
    if configured_workflows is None:
        workflows: tuple[str, ...] = (default_workflow,)
    else:
        workflows = tuple(configured_workflows)
    return WorkerConfig(
        host=worker.get("host", adapter_options.get("host", _DEFAULT_TEMPORAL_HOST)),
        namespace=worker.get("namespace", adapter_options.get("namespace", "default")),
        task_queue=worker.get(
            "task_queue", adapter_options.get("task_queue", "prometheus-pipeline")
        ),
        workflows=workflows,
        activities=worker.get("activities"),
        metrics=TemporalWorkerMetrics(
            prometheus_port=metrics_config.get("prometheus_port"),
            otlp_endpoint=metrics_config.get("otlp_endpoint"),
            dashboard_links=list(metrics_config.get("dashboards", [])),
        ),
    )

