"""Tests for the upgrade planner script."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import upgrade_planner


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _build_basic_sbom(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "sbom.json",
        {
            "components": [
                {"name": "example", "version": "1.0.0"},
                {"name": "pydantic", "version": "1.10.0"},
            ]
        },
    )


def _build_metadata(
    tmp_path: Path, *, example_latest: str = "1.0.1", pydantic_latest: str = "2.0.0"
) -> Path:
    return _write_json(
        tmp_path / "metadata.json",
        {
            "packages": {
                "example": {"latest": example_latest},
                "pydantic": {"latest": pydantic_latest},
            }
        },
    )


def test_generate_plan_runs_resolver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sbom = _build_basic_sbom(tmp_path)
    metadata = _build_metadata(tmp_path)

    calls: list[list[str]] = []

    def fake_run(command, cwd, capture_output, text, env, check):  # type: ignore[no-untyped-def]
        calls.append(command)
        assert command[:3] == ["poetry", "update", "example"]
        assert "--dry-run" in command
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(upgrade_planner.subprocess, "run", fake_run)  # type: ignore[arg-type]

    config = upgrade_planner.PlannerConfig(
        sbom_path=sbom,
        metadata_path=metadata,
        packages=None,
        allow_major=False,
        limit=None,
        poetry_path="poetry",
        project_root=tmp_path,
        skip_resolver=False,
        output_path=None,
        verbose=False,
    )

    result = upgrade_planner.generate_plan(config)

    assert result.summary == {"ok": 1, "failed": 0, "skipped": 0}
    assert result.exit_code == 0
    assert calls
    assert result.recommended_commands == ["poetry update example"]
    attempt = result.attempts[0]
    assert attempt.candidate.score > 0
    assert "severity" in attempt.candidate.score_breakdown


def test_generate_plan_resolver_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sbom = _build_basic_sbom(tmp_path)
    metadata = _build_metadata(tmp_path)

    def fake_run(command, cwd, capture_output, text, env, check):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="error")

    monkeypatch.setattr(upgrade_planner.subprocess, "run", fake_run)  # type: ignore[arg-type]

    config = upgrade_planner.PlannerConfig(
        sbom_path=sbom,
        metadata_path=metadata,
        packages=None,
        allow_major=True,
        limit=None,
        poetry_path="poetry",
        project_root=tmp_path,
        skip_resolver=False,
        output_path=None,
        verbose=False,
    )

    result = upgrade_planner.generate_plan(config)

    assert result.summary == {"ok": 0, "failed": 2, "skipped": 0}
    assert result.exit_code == 2
    assert not result.recommended_commands
    scores = [entry.candidate.score for entry in result.attempts]
    assert all(score >= 0 for score in scores)


def test_generate_plan_respects_package_filter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sbom = _build_basic_sbom(tmp_path)
    metadata = _build_metadata(tmp_path)

    def fake_run(command, cwd, capture_output, text, env, check):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(upgrade_planner.subprocess, "run", fake_run)  # type: ignore[arg-type]

    config = upgrade_planner.PlannerConfig(
        sbom_path=sbom,
        metadata_path=metadata,
        packages=frozenset({"example"}),
        allow_major=True,
        limit=None,
        poetry_path="poetry",
        project_root=tmp_path,
        skip_resolver=False,
        output_path=None,
        verbose=False,
    )

    result = upgrade_planner.generate_plan(config)
    assert [entry.candidate.canonical_name for entry in result.attempts] == ["example"]
    assert result.summary == {"ok": 1, "failed": 0, "skipped": 0}
    assert result.attempts[0].candidate.score > 0


def test_main_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sbom = _build_basic_sbom(tmp_path)
    metadata = _build_metadata(tmp_path)
    output = tmp_path / "plan.json"

    monkeypatch.setattr(upgrade_planner, "_resolve_poetry_path", lambda raw: "poetry")

    exit_code = upgrade_planner.main(
        [
            "--sbom",
            str(sbom),
            "--metadata",
            str(metadata),
            "--skip-resolver",
            "--output",
            str(output),
            "--verbose",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["skipped"] == 1

    out = capsys.readouterr().out
    assert "Upgrade Plan Summary" in out
    assert "Scoreboard" in out


def test_main_invalid_poetry_path(tmp_path: Path) -> None:
    sbom = _build_basic_sbom(tmp_path)
    metadata = _build_metadata(tmp_path)

    exit_code = upgrade_planner.main(
        [
            "--sbom",
            str(sbom),
            "--metadata",
            str(metadata),
            "--poetry",
            "definitely-not-a-real-binary",
            "--skip-resolver",
        ]
    )

    assert exit_code == 2
