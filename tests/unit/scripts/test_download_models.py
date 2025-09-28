from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(module_key: str = "scripts.download_models_test"):
    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "download_models.py"
    )
    spec = importlib.util.spec_from_file_location(module_key, script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None
    sys.modules[module_key] = module
    loader.exec_module(module)
    return module


@pytest.fixture()
def download_models_module():
    module = _load_module()
    try:
        yield module
    finally:
        sys.modules.pop(module.__name__, None)


def _set_model_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    hf_dir = tmp_path / "hf"
    st_dir = tmp_path / "sentence"
    spacy_dir = tmp_path / "spacy"
    monkeypatch.setenv("HF_HOME", str(hf_dir))
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(st_dir))
    monkeypatch.setenv("SPACY_HOME", str(spacy_dir))
    return hf_dir.resolve(), st_dir.resolve(), spacy_dir.resolve()


def test_main_downloads_default_models(
    download_models_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hf_dir, st_dir, spacy_dir = _set_model_env(monkeypatch, tmp_path)
    calls: dict[str, object] = {}

    def fake_hf(models, cache_dir, token):
        calls["hf"] = (list(models), cache_dir, token)

    def fake_sentence(models, cache_dir, token):
        calls["sentence"] = (list(models), cache_dir, token)

    def fake_cross(models, token):
        calls["cross"] = (list(models), token)

    def fake_spacy(models):
        calls["spacy"] = list(models)

    monkeypatch.setattr(download_models_module, "_download_hf_snapshots", fake_hf)
    monkeypatch.setattr(
        download_models_module,
        "_warm_sentence_transformers",
        fake_sentence,
    )
    monkeypatch.setattr(download_models_module, "_warm_cross_encoders", fake_cross)
    monkeypatch.setattr(download_models_module, "_download_spacy_models", fake_spacy)

    exit_code = download_models_module.main([])
    assert exit_code == 0
    assert calls["hf"] == (
        download_models_module.DEFAULT_SENTENCE_TRANSFORMERS
        + download_models_module.DEFAULT_CROSS_ENCODERS,
        hf_dir,
        None,
    )
    assert calls["sentence"] == (
        download_models_module.DEFAULT_SENTENCE_TRANSFORMERS,
        st_dir,
        None,
    )
    assert calls["cross"] == (
        download_models_module.DEFAULT_CROSS_ENCODERS,
        None,
    )
    assert calls["spacy"] == download_models_module.DEFAULT_SPACY_MODELS
    assert Path(download_models_module.os.environ["TRANSFORMERS_CACHE"]) == hf_dir
    assert Path(download_models_module.os.environ["SPACY_HOME"]) == spacy_dir


def test_main_respects_skip_flags(
    download_models_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hf_dir, _, spacy_dir = _set_model_env(monkeypatch, tmp_path)
    called_spacy: list[list[str]] = []

    def fail(*args, **kwargs):  # pragma: no cover - should not be hit
        raise AssertionError("transformer downloads were not skipped")

    def fake_spacy(models):
        called_spacy.append(list(models))

    monkeypatch.setattr(download_models_module, "_download_hf_snapshots", fail)
    monkeypatch.setattr(download_models_module, "_warm_sentence_transformers", fail)
    monkeypatch.setattr(download_models_module, "_warm_cross_encoders", fail)
    monkeypatch.setattr(download_models_module, "_download_spacy_models", fake_spacy)

    exit_code = download_models_module.main(["--skip-transformers"])
    assert exit_code == 0
    assert called_spacy == [download_models_module.DEFAULT_SPACY_MODELS]
    assert Path(download_models_module.os.environ["TRANSFORMERS_CACHE"]) == hf_dir
    assert Path(download_models_module.os.environ["SPACY_HOME"]) == spacy_dir

    called_spacy.clear()

    def fail_spacy(*args, **kwargs):  # pragma: no cover - should not be hit
        raise AssertionError("spaCy downloads were not skipped")

    monkeypatch.setattr(download_models_module, "_download_spacy_models", fail_spacy)
    monkeypatch.setattr(
        download_models_module,
        "_download_hf_snapshots",
        lambda models, cache_dir, token: None,
    )
    monkeypatch.setattr(
        download_models_module,
        "_warm_sentence_transformers",
        lambda models, cache_dir, token: None,
    )
    monkeypatch.setattr(
        download_models_module,
        "_warm_cross_encoders",
        lambda models, token: None,
    )

    exit_code = download_models_module.main(["--skip-spacy"])
    assert exit_code == 0
    assert called_spacy == []
    assert Path(download_models_module.os.environ["TRANSFORMERS_CACHE"]) == hf_dir

