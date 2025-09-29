"""Bootstrap helpers for the FastAPI service."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from prometheus.config import PrometheusConfig
from prometheus.pipeline import PrometheusOrchestrator, build_orchestrator

DEFAULT_CONFIG_PATH = Path("configs/defaults/pipeline_local.toml")


class APISettingsError(Exception):
    """Raised when the API configuration cannot be loaded."""


@lru_cache(maxsize=1)
def get_config_path() -> Path:
    """Resolve the configuration path from environment variables."""

    raw_path = os.getenv("PROMETHEUS_CONFIG")
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    return (DEFAULT_CONFIG_PATH).resolve()


@lru_cache(maxsize=1)
def get_orchestrator() -> PrometheusOrchestrator:
    """Load pipeline configuration and build an orchestrator instance."""

    config_path = get_config_path()
    if not config_path.exists():
        raise APISettingsError(f"Pipeline configuration not found at {config_path}")
    config = PrometheusConfig.load(config_path)
    return build_orchestrator(config)
