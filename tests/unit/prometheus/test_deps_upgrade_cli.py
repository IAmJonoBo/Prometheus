"""Tests for the `prometheus deps upgrade` command."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from prometheus.cli import app

runner = CliRunner()


def _write_sbom(path: Path) -> Path:
    path.write_text(json.dumps({"components": []}), encoding="utf-8")
    return path


def _build_plan_result() -> SimpleNamespace:
    candidate = SimpleNamespace(
        name="example",
        current="1.0.0",
        latest="1.1.0",
        severity="minor",
        score=7.5,
        score_breakdown={"severity": 6.0, "resolver": 1.5},
    )
    resolver = SimpleNamespace(status="ok", reason=None)
    entry = SimpleNamespace(candidate=candidate, resolver=resolver)
    return SimpleNamespace(
        summary={"ok": 1, "failed": 0, "skipped": 0},
        attempts=[entry],
        recommended_commands=["poetry update example"],
        exit_code=0,
    )


def test_deps_upgrade_renders_plan(monkeypatch, tmp_path: Path) -> None:
    sbom = _write_sbom(tmp_path / "sbom.json")

    monkeypatch.setattr(
        "scripts.upgrade_planner._resolve_poetry_path", lambda raw: "poetry"
    )
    monkeypatch.setattr(
        "scripts.upgrade_planner.generate_plan", lambda config: _build_plan_result()
    )

    result = runner.invoke(app, ["deps", "upgrade", "--sbom", str(sbom)])

    assert result.exit_code == 0
    assert "Scoreboard" in result.stdout
    assert "poetry update example" in result.stdout


def test_deps_upgrade_apply_runs_commands(monkeypatch, tmp_path: Path) -> None:
    sbom = _write_sbom(tmp_path / "sbom.json")

    monkeypatch.setattr(
        "scripts.upgrade_planner._resolve_poetry_path", lambda raw: "poetry"
    )
    monkeypatch.setattr(
        "scripts.upgrade_planner.generate_plan", lambda config: _build_plan_result()
    )

    calls: list[tuple[list[str], Path]] = []

    def fake_run(args, cwd, check):  # type: ignore[no-untyped-def]
        calls.append((list(args), cwd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("prometheus.cli.subprocess.run", fake_run)  # type: ignore[arg-type]

    result = runner.invoke(
        app,
        [
            "deps",
            "upgrade",
            "--sbom",
            str(sbom),
            "--apply",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert calls
    command_args, command_cwd = calls[0]
    assert command_args[:3] == ["poetry", "update", "example"]
    assert command_cwd == tmp_path
