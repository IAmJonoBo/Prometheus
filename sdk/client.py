"""Lightweight client helper for Prometheus developers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from prometheus.config import PrometheusConfig
from prometheus.pipeline import (
    PipelineResult,
    PrometheusOrchestrator,
    build_orchestrator,
)


@dataclass(slots=True)
class PrometheusClient:
    """Convenience wrapper that mirrors the CLI pipeline entrypoint."""

    config_path: Path = Path("configs/defaults/pipeline.toml")
    _config: PrometheusConfig | None = field(default=None, init=False, repr=False)
    _orchestrator: PrometheusOrchestrator | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def _load_config(self) -> PrometheusConfig:
        if self._config is None:
            self._config = PrometheusConfig.load(self.config_path)
        return self._config

    def _load_orchestrator(self) -> PrometheusOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = build_orchestrator(self._load_config())
        return self._orchestrator

    def run_pipeline(self, query: str, *, actor: str | None = None) -> PipelineResult:
        """Execute the pipeline and return the structured result."""

        return self._load_orchestrator().run(query, actor=actor)

    def reload(self) -> None:
        """Drop cached configuration and orchestrator instances."""

        self._config = None
        self._orchestrator = None
