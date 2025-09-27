"""Tests for Temporal worker scaffolding."""

from __future__ import annotations

from unittest.mock import patch

from execution.workers import (
    TemporalWorkerConfig,
    TemporalWorkerMetrics,
    build_temporal_worker_plan,
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
