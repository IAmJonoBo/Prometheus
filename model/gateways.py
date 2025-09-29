"""Gateway contracts for model inference backends."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .config import ModelRuntimeConfig


@dataclass(slots=True)
class ModelResponse:
    """Structured response returned by model gateways."""

    text: str
    citations: Sequence[str]
    latency_ms: float


class ModelGateway(Protocol):
    """Protocol implemented by all generation backends."""

    name: str

    async def generate(self, prompt: str, config: ModelRuntimeConfig) -> ModelResponse:
        """Execute a completion request and return a structured response."""
        ...

    async def warm_up(self, config: ModelRuntimeConfig) -> None:
        """Prepare the gateway for traffic (load weights, perform health checks)."""
        ...
