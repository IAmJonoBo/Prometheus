"""Tests for the dry-run debugging utilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from prometheus.debugging import (
    DryRunRecord,
    iter_stage_outputs,
    list_runs,
    load_tracebacks,
    select_run,
)


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _create_run(
    root: Path,
    name: str,
    *,
    completed_at: datetime,
    started_at: datetime | None = None,
    warnings: list[str] | None = None,
    query: str | None = None,
    actor: str | None = None,
    tracebacks: list[dict[str, object]] | None = None,
    manifest_extra: dict[str, object] | None = None,
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    manifest = {
        "run_id": name,
        "completed_at": completed_at.isoformat(),
        "started_at": (started_at or completed_at).isoformat(),
        "warnings": warnings or [],
        "query": query,
        "actor": actor,
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    _write_manifest(run_dir / "manifest.json", manifest)
    if tracebacks is not None:
        (run_dir / "tracebacks.json").write_text(
            json.dumps(tracebacks),
            encoding="utf-8",
        )
    return run_dir


def test_list_runs_orders_by_completion_and_parses_metadata(tmp_path: Path) -> None:
    root = tmp_path / "dryruns"
    root.mkdir()
    older = datetime.now(tz=UTC) - timedelta(hours=1)
    newer = datetime.now(tz=UTC)

    _create_run(
        root,
        "run-1",
        completed_at=older,
        query="older",
        warnings=["warn"],
        tracebacks=[{"stage": "ingestion", "error_message": "fail"}],
    )
    _create_run(
        root,
        "run-2",
        completed_at=newer,
        query="newer",
        actor="alice",
        tracebacks=[],
    )

    records = list_runs(root)
    assert [record.run_id for record in records] == ["run-2", "run-1"]
    latest = records[0]
    assert latest.actor == "alice"
    assert latest.query == "newer"
    assert latest.tracebacks == []


def test_select_run_prefers_requested_identifier(tmp_path: Path) -> None:
    root = tmp_path / "dryruns"
    root.mkdir()
    now = datetime.now(tz=UTC)
    _create_run(root, "run-a", completed_at=now)
    _create_run(root, "run-b", completed_at=now + timedelta(minutes=1))

    latest = select_run(root, None)
    assert latest is not None
    assert latest.run_id == "run-b"

    specific = select_run(root, "run-a")
    assert specific is not None
    assert specific.run_id == "run-a"
    assert select_run(root, "missing") is None


def test_load_tracebacks_prefers_cached_payload(tmp_path: Path) -> None:
    root = tmp_path / "dryruns"
    root.mkdir()
    run_dir = _create_run(
        root,
        "run-cache",
        completed_at=datetime.now(tz=UTC),
        tracebacks=[{"stage": "retrieval", "error_message": "boom"}],
    )
    record = list_runs(root)[0]
    # Cached tracebacks should be returned without hitting the file again.
    run_dir.joinpath("tracebacks.json").write_text("[]", encoding="utf-8")
    assert load_tracebacks(record) == [{"stage": "retrieval", "error_message": "boom"}]


def test_load_tracebacks_falls_back_to_file(tmp_path: Path) -> None:
    root = tmp_path / "dryruns"
    root.mkdir()
    run_dir = _create_run(
        root,
        "run-file",
        completed_at=datetime.now(tz=UTC),
        tracebacks=None,
    )
    run_dir.joinpath("tracebacks.json").write_text(
        json.dumps([{"stage": "decision", "error_message": "oops"}]),
        encoding="utf-8",
    )
    record = DryRunRecord(
        run_id="run-file",
        root=run_dir,
        manifest={},
        started_at=None,
        completed_at=None,
        actor=None,
        query=None,
        warnings=[],
        tracebacks=[],
    )
    assert load_tracebacks(record) == [{"stage": "decision", "error_message": "oops"}]


@pytest.mark.parametrize(
    "stage_outputs, expected",
    [
        ({"a": "path/a", "b": "path/b"}, (("a", "path/a"), ("b", "path/b"))),
        ({}, ()),
        (None, ()),
    ],
)
def test_iter_stage_outputs_returns_sorted_pairs(stage_outputs, expected) -> None:
    manifest = {"stage_outputs": stage_outputs}
    assert iter_stage_outputs(manifest) == expected
