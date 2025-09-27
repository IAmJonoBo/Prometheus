"""Pipeline orchestration for Prometheus."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

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
    build_temporal_worker_plan,
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
    worker_plan = _build_worker_plan(config.execution)
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
    return orchestrator


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
            target_host=options.get("host", "localhost:7233"),
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


def _build_worker_plan(config: ExecutionConfig) -> TemporalWorkerPlan | None:
    if config.sync_target != "temporal":
        return None
    worker = config.worker or {}
    adapter_options = config.adapter or {}
    metrics_config = worker.get("metrics", {})
    default_workflow = adapter_options.get("workflow", "PrometheusPipeline")
    configured_workflows = worker.get("workflows")
    if configured_workflows is None:
        workflows: tuple[str, ...] = (default_workflow,)
    else:
        workflows = tuple(configured_workflows)
    plan_config = WorkerConfig(
        host=worker.get("host", adapter_options.get("host", "localhost:7233")),
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
    return build_temporal_worker_plan(plan_config)

