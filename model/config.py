"""Configuration objects for model selection and runtime tuning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ModelSelection:
    """Represents the chosen generation and embedding backends."""

    generation: str = "vllm"
    embedding: str = "sentence-transformers"
    reranker: str = "sentence-transformers"


@dataclass(slots=True)
class ModelRuntimeConfig:
    """Holds runtime tuning knobs shared across gateways."""

    max_input_tokens: int = 4096
    max_output_tokens: int = 512
    temperature: float = 0.2
    top_p: float = 0.95
    selection: ModelSelection = ModelSelection()

    def with_selection(self, selection: ModelSelection) -> ModelRuntimeConfig:
        return ModelRuntimeConfig(
            max_input_tokens=self.max_input_tokens,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            selection=selection,
        )
