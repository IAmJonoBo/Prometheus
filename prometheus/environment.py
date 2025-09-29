"""Environment helpers for Prometheus runtime caches."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _default_paths() -> dict[str, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    model_root = repo_root / "vendor" / "models"
    return {
        "HF_HOME": model_root / "hf",
        "TRANSFORMERS_CACHE": model_root / "hf",
        "HUGGINGFACE_HUB_CACHE": model_root / "hf",
        "SENTENCE_TRANSFORMERS_HOME": model_root / "sentence-transformers",
        "SPACY_HOME": model_root / "spacy",
    }


@lru_cache(maxsize=1)
def ensure_local_cache_env() -> dict[str, str]:
    """Populate cache-related environment variables under ``vendor/``.

    The repository is often mounted on external storage; this helper ensures
    Hugging Face, Sentence-Transformers, and spaCy artefacts are stored beneath
    ``vendor/models`` so every checkout co-locates its dependent assets.

    Returns
    -------
    Dict[str, str]
        Mapping of environment variables that were set by this call.
    """

    updates: dict[str, str] = {}
    for variable, path in _default_paths().items():
        if os.getenv(variable):
            continue
        path.mkdir(parents=True, exist_ok=True)
        value = str(path)
        os.environ[variable] = value
        updates[variable] = value
    return updates
