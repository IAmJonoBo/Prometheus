"""Pipeline orchestration for Prometheus."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from common.contracts import (
    DecisionRecorded,
    ExecutionPlanDispatched,
    IngestionNormalised,
    MonitoringSignal,
    ReasoningAnalysisProposed,
    RetrievalContextBundle,
)
from common.events import EventBus, EventFactory
from decision.service import DecisionService
from execution.service import ExecutionAdapter, ExecutionService
from ingestion.service import IngestionService
from monitoring.service import MonitoringService, SignalCollector
from reasoning.service import ReasoningService
from retrieval.service import InMemoryRetriever, RetrievalService

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
        evidence = list(self._ingestion.collect())
        normalised = self._ingestion.normalise(evidence, factory)
        for event in normalised:
            self._bus.publish(event)

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
        signal = self._monitoring.build_signal(decision, monitoring_meta)
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
    retriever = InMemoryRetriever()
    retrieval = RetrievalService(config.retrieval, retriever)
    reasoning = ReasoningService(config.reasoning)
    decision = DecisionService(config.decision)
    execution_adapter = _InMemoryExecutionAdapter()
    execution = ExecutionService(config.execution, execution_adapter)
    collector = _InMemorySignalCollector()
    monitoring = MonitoringService(config.monitoring, [collector])
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
    orchestrator.signal_collectors = [collector]
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

