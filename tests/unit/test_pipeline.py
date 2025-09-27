"""Bootstrap tests for the Prometheus pipeline."""

from __future__ import annotations

from typing import Any, cast

from prometheus import PrometheusConfig, build_orchestrator


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
