"""Tests for Temporal worker scaffolding."""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import patch

from execution.workers import (
    TemporalWorkerConfig,
    TemporalWorkerMetrics,
    _TelemetryBootstrap,
    build_temporal_worker_plan,
    create_temporal_worker_runtime,
    validate_temporal_worker_plan,
)


def test_temporal_worker_plan_marks_missing_dependency() -> None:
    config = TemporalWorkerConfig(task_queue="demo-queue")
    with patch("execution.workers._module_available", return_value=False):
        plan = build_temporal_worker_plan(config)

    assert plan.ready is False
    assert any("temporalio" in note for note in plan.notes)
    assert plan.connection["task_queue"] == "demo-queue"


def test_temporal_worker_plan_carries_metrics_config() -> None:
    config = TemporalWorkerConfig(
        metrics=TemporalWorkerMetrics(
            prometheus_port=9095,
            otlp_endpoint="grpc://collector:4317",
        )
    )
    with patch("execution.workers._module_available", return_value=True):
        plan = build_temporal_worker_plan(config)

    assert plan.ready is True
    assert plan.instrumentation["prometheus_port"] == 9095
    assert plan.instrumentation["otlp_endpoint"] == "grpc://collector:4317"


def test_create_temporal_worker_runtime_skips_when_not_ready() -> None:
    config = TemporalWorkerConfig()
    with patch("execution.workers._module_available", return_value=False):
        runtime = create_temporal_worker_runtime(config)

    assert runtime is None


def test_create_temporal_worker_runtime_uses_defaults() -> None:
    config = TemporalWorkerConfig()
    with patch("execution.workers._module_available", return_value=True):
        runtime = create_temporal_worker_runtime(config)

    assert runtime is not None
    assert runtime.plan.ready is True
    workflow_names = {workflow.__name__ for workflow in runtime.workflows}
    assert "PrometheusPipelineWorkflow" in workflow_names
    assert "DependencySnapshotWorkflow" in workflow_names
    assert set(runtime.activities) == {
        "record_decision",
        "emit_metrics",
        "run_dependency_snapshot",
        "notify_dependency_snapshot",
    }


def test_telemetry_bootstrap_gracefully_handles_missing_dependencies() -> None:
    bootstrap = _TelemetryBootstrap({})
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bootstrap.__aenter__())
        loop.run_until_complete(bootstrap.__aexit__(None, None, None))
    finally:
        loop.close()


def test_telemetry_bootstrap_starts_prometheus_server() -> None:
    captured: dict[str, int] = {}

    prometheus_stub = types.ModuleType("prometheus_client")

    def _start_http_server(port: int) -> None:
        captured["port"] = port

    prometheus_stub.start_http_server = _start_http_server  # type: ignore[attr-defined]
    sys.modules["prometheus_client"] = prometheus_stub
    bootstrap = _TelemetryBootstrap({"prometheus_port": 9123})
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bootstrap.__aenter__())
        assert captured["port"] == 9123
        loop.run_until_complete(bootstrap.__aexit__(None, None, None))
    finally:
        loop.close()
        sys.modules.pop("prometheus_client", None)


def test_validate_temporal_worker_plan_reports_status(monkeypatch) -> None:
    config = TemporalWorkerConfig(
        metrics=TemporalWorkerMetrics(
            prometheus_port=9464,
            otlp_endpoint="grpc://collector:4317",
            dashboard_links=["grafana://prom-ingest-001"],
        )
    )

    monkeypatch.setattr("execution.workers._module_available", lambda _: True)
    probe_results = iter([True, True, False])
    monkeypatch.setattr(
        "execution.workers._probe_endpoint",
        lambda *_, **__: next(probe_results),
    )

    dashboards = [types.SimpleNamespace(uid="prom-ingest-001")]
    report = validate_temporal_worker_plan(config, known_dashboards=dashboards)

    assert report.is_ready is True
    assert any(check.label == "Temporal gRPC" for check in report.checks)
    assert report.dashboards["grafana://prom-ingest-001"] is True


def test_validate_temporal_worker_plan_handles_missing_dependency(monkeypatch) -> None:
    config = TemporalWorkerConfig()
    monkeypatch.setattr("execution.workers._module_available", lambda _: False)
    monkeypatch.setattr("execution.workers._probe_endpoint", lambda *_, **__: False)

    report = validate_temporal_worker_plan(config, known_dashboards=None)

    assert report.is_ready is False
    assert all(report.dashboards.values())
