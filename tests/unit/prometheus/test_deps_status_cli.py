"""Tests for the `prometheus deps status` command."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from chiron.deps.status import DependencyStatus, GuardRun, PlannerRun
from prometheus.cli import app

runner = CliRunner()


def _build_status(**overrides: Any) -> DependencyStatus:
    moment = overrides.pop("generated_at", datetime.now(UTC))
    guard = overrides.pop(
        "guard",
        GuardRun(
            exit_code=0,
            assessment={
                "summary": {
                    "highest_severity": "safe",
                    "packages_flagged": 0,
                    "contract_risk": "safe",
                    "drift_severity": "safe",
                    "notes": ["All good"],
                }
            },
            markdown="# Guard Summary\nAll clear.",
        ),
    )
    planner = overrides.pop(
        "planner",
        PlannerRun(
            exit_code=0,
            plan={"summary": {"ok": 1}},
            error=None,
        ),
    )
    summary = overrides.pop(
        "summary",
        {
            "generated_at": moment.isoformat(),
            "highest_severity": "safe",
            "packages_flagged": 0,
            "contract_risk": "safe",
            "drift_severity": "safe",
            "notes": ["All good"],
            "guard_exit_code": guard.exit_code,
            "planner_exit_code": planner.exit_code,
            "planner_summary": planner.summary,
            "planner_error": planner.error,
            "planner_reason": None,
            "recommended_commands": ["poetry update example"],
        },
    )
    exit_code = overrides.pop("exit_code", 0)
    if overrides:
        raise ValueError(f"Unexpected overrides: {sorted(overrides)}")
    return DependencyStatus(moment, guard, planner, exit_code, summary)


def test_deps_status_outputs_json_and_summary(monkeypatch, tmp_path: Path) -> None:
    contract = tmp_path / "contract.toml"
    contract.write_text("[contract]\nstatus='safe'\n", encoding="utf-8")

    status = _build_status()

    captured_kwargs: dict[str, Any] = {}

    def fake_generate_status(**kwargs: Any) -> DependencyStatus:
        captured_kwargs.update(kwargs)
        return status

    monkeypatch.setattr("scripts.deps_status.generate_status", fake_generate_status)

    result = runner.invoke(
        app,
        [
            "deps",
            "status",
            "--contract",
            str(contract),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured_kwargs["preflight"] is None
    assert captured_kwargs["sbom"] is None
    assert "Dependency status: safe" in result.stdout

    json_text, _, remainder = result.stdout.partition("Dependency status:")
    payload = json.loads(json_text.strip())
    assert payload["summary"]["highest_severity"] == "safe"
    assert remainder.startswith("safe")


def test_deps_status_handles_inputs_and_markdown(monkeypatch, tmp_path: Path) -> None:
    contract = tmp_path / "contract.toml"
    contract.write_text("[contract]\nstatus='safe'\n", encoding="utf-8")

    sbom = tmp_path / "sbom.json"
    sbom.write_text("{}", encoding="utf-8")

    status = _build_status()

    captured_kwargs: dict[str, Any] = {}

    def fake_generate_status(**kwargs: Any) -> DependencyStatus:
        captured_kwargs.update(kwargs)
        return status

    monkeypatch.setattr("scripts.deps_status.generate_status", fake_generate_status)

    markdown_path = tmp_path / "status.md"

    result = runner.invoke(
        app,
        [
            "deps",
            "status",
            "--contract",
            str(contract),
            "--input",
            f"sbom={sbom}",
            "--markdown-output",
            str(markdown_path),
            "--show-markdown",
        ],
    )

    assert result.exit_code == 0
    assert captured_kwargs["sbom"] == sbom.resolve()
    assert markdown_path.read_text(encoding="utf-8") == status.guard.markdown
    assert "Guard summary:" in result.stdout
    assert "All clear." in result.stdout
