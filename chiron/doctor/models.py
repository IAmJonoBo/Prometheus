#!/usr/bin/env python3
"""Download Prometheus model artefacts for offline environments.

This helper pre-populates the caches used by Sentence-Transformers, Hugging
Face, and spaCy so that air-gapped runners can execute the pipeline without
reaching out to the public internet. By default it downloads the embedding and
reranker checkpoints plus the spaCy pipeline required by the PII toolchain, but
additional artefacts can be requested through CLI flags.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from huggingface_hub import snapshot_download as _snapshot_download
    from sentence_transformers import CrossEncoder as _CrossEncoder
    from sentence_transformers import SentenceTransformer as _SentenceTransformer
    from spacy.cli import download as _spacy_download
    from spacy.util import get_package_path as _get_package_path

DEFAULT_SENTENCE_TRANSFORMERS = [
    "sentence-transformers/all-MiniLM-L6-v2",
]
DEFAULT_CROSS_ENCODERS = [
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
]
DEFAULT_SPACY_MODELS = [
    "en_core_web_lg",
]


def _ensure_env_path(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    path = Path(value) if value else default
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    os.environ[variable] = str(path)
    return path


def _download_hf_snapshots(
    repo_ids: Iterable[str],
    cache_dir: Path,
    token: str | None,
) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "huggingface-hub is required but not installed. Did you install the "
            "project dependencies?"
        ) from exc

    for repo_id in dict.fromkeys(repo_ids):
        print(f"→ Ensuring Hugging Face snapshot for {repo_id}")
        snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            token=token,
            resume_download=True,
        )


def _warm_sentence_transformers(
    model_names: Iterable[str],
    cache_dir: Path,
    token: str | None,
) -> None:
    if not model_names:
        return
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "sentence-transformers is required but not installed. "
            "Ensure the base dependencies are available before running this "
            "script."
        ) from exc

    for model_name in dict.fromkeys(model_names):
        print(f"→ Caching sentence-transformer {model_name}")
        model = SentenceTransformer(
            model_name,
            device="cpu",
            cache_folder=str(cache_dir),
            use_auth_token=token,
        )
        del model


def _warm_cross_encoders(
    model_names: Iterable[str],
    token: str | None,
) -> None:
    if not model_names:
        return
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "sentence-transformers is required but not installed. "
            "Ensure the base dependencies are available before running this "
            "script."
        ) from exc

    for model_name in dict.fromkeys(model_names):
        print(f"→ Caching cross-encoder {model_name}")
        try:
            model = CrossEncoder(
                model_name,
                device="cpu",
                use_auth_token=token,
            )
        except TypeError as exc:  # pragma: no cover - compatibility shim
            message = str(exc)
            if "unexpected keyword argument 'use_auth_token'" not in message:
                raise
            model = CrossEncoder(model_name, device="cpu")
        del model


def _download_spacy_models(model_names: Iterable[str]) -> None:
    if not model_names:
        return
    try:
        from spacy.cli import download as spacy_download
        from spacy.util import get_package_path
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "spaCy is required but not installed. Install the pii extra or run "
            "poetry install before downloading the pipelines."
        ) from exc

    for model_name in dict.fromkeys(model_names):
        print(f"→ Downloading spaCy pipeline {model_name}")
        target_dir = Path(os.environ["SPACY_HOME"]).resolve()
        spacy_download(model_name, False, False, "--target", str(target_dir))
        location = get_package_path(model_name)
        print(f"  ↳ Stored at {location}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pre-download Prometheus model artefacts for air-gapped installs. "
            "Run from the repository root after setting HF/SPACY homes if "
            "custom locations are required."
        )
    )
    parser.add_argument(
        "--hf-token",
        dest="hf_token",
        help="Hugging Face access token for private models (optional).",
    )
    parser.add_argument(
        "--sentence-transformer",
        dest="sentence_models",
        action="append",
        help=(
            "Sentence-Transformers model to cache. Can be provided multiple "
            "times. Defaults to all-MiniLM-L6-v2."
        ),
    )
    parser.add_argument(
        "--cross-encoder",
        dest="cross_models",
        action="append",
        help=(
            "Cross-encoder model to cache. Can be provided multiple times. "
            "Defaults to ms-marco-MiniLM-L-6-v2."
        ),
    )
    parser.add_argument(
        "--spacy-model",
        dest="spacy_models",
        action="append",
        help=(
            "spaCy pipeline to download. Can be provided multiple times. "
            "Defaults to en_core_web_lg."
        ),
    )
    parser.add_argument(
        "--skip-spacy",
        action="store_true",
        help="Skip spaCy downloads (useful when the PII extra is disabled).",
    )
    parser.add_argument(
        "--skip-transformers",
        action="store_true",
        help="Skip Sentence-Transformer and cross-encoder downloads.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    model_root = repo_root / "vendor" / "models"

    hf_home = _ensure_env_path("HF_HOME", model_root / "hf")
    sentence_home = _ensure_env_path(
        "SENTENCE_TRANSFORMERS_HOME", model_root / "sentence-transformers"
    )
    spacy_home = _ensure_env_path("SPACY_HOME", model_root / "spacy")
    os.environ["TRANSFORMERS_CACHE"] = str(hf_home)

    sentence_models = args.sentence_models or list(DEFAULT_SENTENCE_TRANSFORMERS)
    cross_models = args.cross_models or list(DEFAULT_CROSS_ENCODERS)
    spacy_models = args.spacy_models or list(DEFAULT_SPACY_MODELS)

    hf_repos: list[str] = []
    if not args.skip_transformers:
        hf_repos.extend(sentence_models)
        hf_repos.extend(cross_models)

    print("Preparing model artefacts…")
    print(f"• HF cache: {hf_home}")
    print(f"• Sentence-Transformers cache: {sentence_home}")
    if not args.skip_spacy:
        print(f"• spaCy data path: {spacy_home}")
    else:
        print("• spaCy downloads skipped")

    token = args.hf_token or os.environ.get("HUGGINGFACEHUB_API_TOKEN")

    if hf_repos:
        _download_hf_snapshots(hf_repos, hf_home, token)
        _warm_sentence_transformers(sentence_models, sentence_home, token)
        _warm_cross_encoders(cross_models, token)
    else:
        print("Skipped Sentence-Transformers downloads")

    if not args.skip_spacy:
        _download_spacy_models(spacy_models)
    return 0


if __name__ == "__main__":
    sys.exit(main())
