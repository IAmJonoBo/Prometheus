"""Configuration loader for Prometheus pipeline bootstrap."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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

    runtime: RuntimeConfig
    ingestion: IngestionConfig
    retrieval: RetrievalConfig
    reasoning: ReasoningConfig
    decision: DecisionConfig
    execution: ExecutionConfig
    monitoring: MonitoringConfig

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> PrometheusConfig:
        """Construct configuration from a mapping structure."""

        ingestion_data = dict(data["ingestion"])
        raw_sources = ingestion_data.get("sources", [])
        normalised_sources: list[dict[str, Any]] = []
        for source in raw_sources:
            if isinstance(source, dict):
                normalised_sources.append(source)
            elif isinstance(source, str):
                if source.startswith("file://"):
                    normalised_sources.append(
                        {"type": "filesystem", "root": source[7:]}
                    )
                elif source.startswith("http"):
                    normalised_sources.append({"type": "web", "urls": [source]})
                else:
                    normalised_sources.append({"type": "memory", "uri": source})
        ingestion_data["sources"] = normalised_sources

        retrieval_data = dict(data["retrieval"])
        retrieval_data.setdefault("lexical", retrieval_data.get("lexical"))
        retrieval_data.setdefault("vector", retrieval_data.get("vector"))
        retrieval_data.setdefault("reranker", retrieval_data.get("reranker"))

        execution_data = dict(data["execution"])
        monitoring_data = dict(data["monitoring"])

        runtime_data = dict(data.get("runtime", {}))
        runtime = RuntimeConfig(**runtime_data)

        return cls(
            runtime=runtime,
            ingestion=IngestionConfig(**ingestion_data),
            retrieval=RetrievalConfig(**retrieval_data),
            reasoning=ReasoningConfig(**data["reasoning"]),
            decision=DecisionConfig(**data["decision"]),
            execution=ExecutionConfig(**execution_data),
            monitoring=MonitoringConfig(**monitoring_data),
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


@dataclass(slots=True, kw_only=True)
class RuntimeConfig:
    """Global runtime options controlling pipeline execution."""

    mode: str = "production"
    allow_side_effects: bool = False
    artifact_root: str = "var/runs"
    fixtures_root: str | None = None
    retention_days: int = 30
    feature_flags: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in {"production", "dry-run", "staging"}:
            raise ValueError(
                "runtime.mode must be one of 'production', 'dry-run', or 'staging'"
            )
        if self.retention_days <= 0:
            raise ValueError("runtime.retention_days must be positive")
