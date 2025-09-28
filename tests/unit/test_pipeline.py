"""Bootstrap tests for the Prometheus pipeline."""

from __future__ import annotations

import logging
from typing import Any, cast
from unittest.mock import patch

from prometheus import PrometheusConfig, build_orchestrator
from prometheus.pipeline import _verify_external_dependencies


def _config() -> PrometheusConfig:
    return PrometheusConfig.from_mapping(
        {
            "ingestion": {"sources": ["memory://test-source"]},
            "retrieval": {
                "strategy": "hybrid",
                "max_results": 5,
                "lexical": {"backend": "rapidfuzz"},
            },
            "reasoning": {"planner": "sequential", "max_tokens": 512},
            "decision": {"policy_engine": "policy.simple"},
            "execution": {"sync_target": "in-memory"},
            "monitoring": {"sample_rate": 1.0},
        }
    )


def test_pipeline_emits_events_and_records_audit_trail() -> None:
    orchestrator = build_orchestrator(_config())
    result = orchestrator.run("configured")

    assert result.decision.status == "approved"
    assert result.ingestion[0].attachments
    assert result.ingestion[0].provenance["content"]
    adapter = cast(Any, orchestrator.execution_adapter)
    assert adapter is not None
    assert adapter.notes
    collector = cast(Any, orchestrator.signal_collectors[0])
    assert collector.signals
    signal = collector.signals[0]
    assert any(metric.name.startswith("ingestion.") for metric in signal.metrics)

    events = list(orchestrator.bus.replay())
    assert len(events) >= 5

    audit_plugin = next(iter(orchestrator.registry.plugins()))
    assert audit_plugin.events  # type: ignore[attr-defined]


def test_pipeline_exposes_temporal_worker_runtime() -> None:
    config = _config()
    config.execution.sync_target = "temporal"
    config.execution.adapter = {
        "workflow": "PrometheusPipeline",
        "host": "localhost:7233",
        "namespace": "default",
    }
    config.execution.worker = {
        "metrics": {
            "prometheus_port": 9501,
            "dashboards": ["https://grafana.local/d/worker"],
        }
    }

    with patch("execution.workers._module_available", return_value=True):
        orchestrator = build_orchestrator(config)

    assert orchestrator.worker_plan is not None
    assert orchestrator.worker_plan.ready is True
    assert orchestrator.worker_plan.instrumentation["prometheus_port"] == 9501
    assert orchestrator.worker_runtime is not None
    assert orchestrator.worker_runtime.plan is orchestrator.worker_plan
    assert any(
        workflow.__name__ == "PrometheusPipelineWorkflow"
        for workflow in orchestrator.worker_runtime.workflows
    )


def test_verify_external_dependencies_logs_warnings(monkeypatch, caplog) -> None:
    config = PrometheusConfig.from_mapping(
        {
            "ingestion": {"sources": ["memory://dependency-check"]},
            "retrieval": {
                "strategy": "hybrid",
                "max_results": 5,
                "lexical": {"backend": "opensearch"},
                "vector": {
                    "backend": "qdrant",
                    "url": "http://localhost:6333",
                },
            },
            "reasoning": {"planner": "sequential", "max_tokens": 256},
            "decision": {"policy_engine": "policy.simple"},
            "execution": {
                "sync_target": "temporal",
                "adapter": {"host": "localhost:7233"},
            },
            "monitoring": {
                "sample_rate": 1.0,
                "collectors": [
                    {
                        "type": "prometheus",
                        "gateway_url": "http://localhost:9091",
                    }
                ],
            },
        }
    )

    monkeypatch.setattr(
        "prometheus.pipeline._probe_endpoint",
        lambda endpoint, timeout=1.0: False,
    )

    with caplog.at_level(logging.WARNING):
        _verify_external_dependencies(config)

    text = caplog.text
    assert "OpenSearch host" in text
    assert "Qdrant endpoint" in text
    assert "Temporal host" in text
    assert "Prometheus Pushgateway" in text
