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
from ingestion.service import IngestionService
from monitoring.collectors import build_collector
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

