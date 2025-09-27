"""CLI tests for the retrieval regression harness."""

from __future__ import annotations

import json
from pathlib import Path

from retrieval import regression_cli


def _write_dataset(tmp_path: Path, *, min_hits: int = 1) -> Path:
    content = f"""
top_k = 1

[thresholds]
min_hits = {min_hits}
min_recall_at_k = 0.5
min_mean_reciprocal_rank = 0.5

[[documents]]
uri = "doc://alpha"
source_system = "seed"
content = "alpha"

[[samples]]
query = "alpha"
relevant_uris = ["doc://alpha"]
"""
    dataset = tmp_path / "dataset.toml"
    dataset.write_text(content, encoding="utf-8")
    return dataset


def test_cli_reports_sample_details(tmp_path, capsys) -> None:
    dataset = _write_dataset(tmp_path)

    exit_code = regression_cli.main([str(dataset)])
    captured = capsys.readouterr().out

    assert exit_code == 0
    payload = json.loads(captured)
    assert payload["status"] == "passed"
    assert payload["samples"][0]["hit"] is True
    assert payload["samples"][0]["retrieved_uris"] == ["doc://alpha"]


def test_cli_reports_sample_details_on_failure(tmp_path, capsys) -> None:
    dataset = _write_dataset(tmp_path, min_hits=2)

    exit_code = regression_cli.main([str(dataset)])
    captured = capsys.readouterr().out

    assert exit_code == 1
    payload = json.loads(captured)
    assert payload["status"] == "failed"
    assert payload["samples"][0]["hit"] is True
