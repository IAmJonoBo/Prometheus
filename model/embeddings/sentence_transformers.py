# ruff: noqa: I001 - placeholder awaiting concrete implementation
"""Sentence-Transformers embedding stub."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

DEFAULT_MODEL = "sentence-transformers/all-mpnet-base-v2"


def embed_texts(
    texts: Iterable[str], model_name: str = DEFAULT_MODEL
) -> Sequence[float]:
    """Placeholder embedding routine awaiting a concrete implementation."""

    raise NotImplementedError(
        "Install sentence-transformers and compute embeddings for the supplied texts."
    )
