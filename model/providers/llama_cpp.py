"""llama.cpp gateway stub."""

from __future__ import annotations

from pathlib import Path

from ..config import ModelRuntimeConfig
from ..gateways import ModelGateway, ModelResponse


class LlamaCppGateway(ModelGateway):
    """Placeholder adapter for CPU/offline llama.cpp execution."""

    name = "llama.cpp"

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path or Path("var/models/default.gguf")

    async def generate(self, prompt: str, config: ModelRuntimeConfig) -> ModelResponse:
        raise NotImplementedError(
            "Wire llama.cpp bindings (for example llama-cpp-python) before use."
        )

    async def warm_up(self, config: ModelRuntimeConfig) -> None:
        raise NotImplementedError("Load the quantised GGUF weights into memory.")
