"""vLLM gateway stub."""

from __future__ import annotations

from typing import Any

from ..config import ModelRuntimeConfig
from ..gateways import ModelGateway, ModelResponse


class VLLMGateway(ModelGateway):
    """Placeholder adapter for a vLLM inference deployment."""

    name = "vllm"

    def __init__(
        self, endpoint: str = "http://localhost:8001", **client_kwargs: Any
    ) -> None:
        self._endpoint = endpoint
        self._client_kwargs = client_kwargs

    async def generate(self, prompt: str, config: ModelRuntimeConfig) -> ModelResponse:
        raise NotImplementedError(
            "Integrate with your vLLM deployment (HTTP or gRPC) before use."
        )

    async def warm_up(self, config: ModelRuntimeConfig) -> None:
        raise NotImplementedError("Issue a lightweight readiness probe to vLLM.")
