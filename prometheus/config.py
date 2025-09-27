"""Configuration loader for Prometheus pipeline bootstrap."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decision.service import DecisionConfig
from execution.service import ExecutionConfig
from ingestion.service import IngestionConfig
from monitoring.service import MonitoringConfig
from reasoning.service import ReasoningConfig
from retrieval.service import RetrievalConfig


@dataclass(slots=True, kw_only=True)
class PrometheusConfig:
    """Container for stage configuration objects."""

    ingestion: IngestionConfig
    retrieval: RetrievalConfig
    reasoning: ReasoningConfig
    decision: DecisionConfig
    execution: ExecutionConfig
    monitoring: MonitoringConfig

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> PrometheusConfig:
        """Construct configuration from a mapping structure."""

        return cls(
            ingestion=IngestionConfig(**data["ingestion"]),
            retrieval=RetrievalConfig(**data["retrieval"]),
            reasoning=ReasoningConfig(**data["reasoning"]),
            decision=DecisionConfig(**data["decision"]),
            execution=ExecutionConfig(**data["execution"]),
            monitoring=MonitoringConfig(**data["monitoring"]),
        )

    @classmethod
    def load(cls, path: Path) -> PrometheusConfig:
        """Load configuration from a TOML or JSON document."""

        suffix = path.suffix.lower()
        if suffix == ".toml":
            import tomllib

            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        elif suffix == ".json":
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            raise ValueError(f"Unsupported config format: {path}")
        return cls.from_mapping(payload)

