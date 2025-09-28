"""Reference Temporal workflows and activities for Prometheus execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional dependency wiring
    from temporalio import activity, workflow
except ImportError:  # pragma: no cover - fallback when temporalio missing
    def _identity_decorator(target=None, **_: Any):
        if target is not None:
            return target

        def decorator(func):
            return func

        return decorator

    class _WorkflowStub:
        def defn(self, target=None, **kwargs: Any):
            return _identity_decorator(target, **kwargs)

        def run(self, target=None, **kwargs: Any):
            return _identity_decorator(target, **kwargs)

    class _ActivityStub:
        def defn(self, target=None, **kwargs: Any):
            return _identity_decorator(target, **kwargs)

    workflow = _WorkflowStub()  # type: ignore
    activity = _ActivityStub()  # type: ignore


@dataclass(slots=True)
class WorkerContext:
    """Context emitted by the default workflow/activity pair."""

    decision_id: str
    notes: list[str]
    status: str


@workflow.defn
class PrometheusPipelineWorkflow:
    """Temporal workflow that mirrors decision payloads for auditing."""

    @workflow.run
    async def run(self, decision_payload: dict[str, Any]) -> WorkerContext:
        event_id = decision_payload.get("meta", {}).get("event_id", "unknown")
        notes = decision_payload.get("notes", [])
        return WorkerContext(decision_id=event_id, notes=list(notes), status="received")


@activity.defn
async def record_decision_activity(context: WorkerContext) -> dict[str, Any]:
    """Return a structured log payload for downstream sinks."""

    return {
        "decision_id": context.decision_id,
        "status": context.status,
        "note_count": len(context.notes),
    }


@activity.defn
async def emit_metrics_activity(context: WorkerContext) -> dict[str, Any]:
    """Provide metric-friendly representation for monitoring exporters."""

    return {
        "metric": "temporal.worker.decisions.processed",
        "value": 1.0,
        "attributes": {
            "decision_id": context.decision_id,
            "status": context.status,
        },
    }
