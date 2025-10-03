"""Tests for the dependency status aggregation helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from prometheus import cli as prometheus_cli
from scripts import deps_status


class _DummyPlanResult:
    exit_code = 0

    def __init__(
        self, summary: dict[str, int] | None = None, commands: list[str] | None = None
    ) -> None:
        self._summary = summary or {"upgrades_planned": 2}
        self._commands = commands or ["poetry update fastapi"]

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self._summary,
            "recommended_commands": self._commands,
        }


def _stub_guard(summary_payload: dict[str, Any]) -> Callable[[list[str]], int]:
    def _run(argv: list[str]) -> int:
        options: dict[str, str] = {}
        iterator = iter(argv)
        for flag in iterator:
            options[flag] = next(iterator)
        Path(options["--output"]).write_text(
            json.dumps(summary_payload),
            encoding="utf-8",
        )
        Path(options["--markdown"]).write_text("Guard markdown", encoding="utf-8")
        return 0

    return _run


def test_generate_status_combines_guard_and_planner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary_payload = {
        "summary": {
            "highest_severity": "ok",
            "packages_flagged": 1,
            "contract_risk": "low",
            "drift_severity": "none",
            "notes": ["all clear"],
        },
        "contract": {"risk": "ok", "status": "active"},
        "drift": {"severity": "none"},
    }

    monkeypatch.setattr(deps_status.upgrade_guard, "main", _stub_guard(summary_payload))

    captured_config: dict[str, Any] = {}

    def _fake_generate_plan(config: object) -> _DummyPlanResult:
        captured_config["config"] = config
        return _DummyPlanResult()

    monkeypatch.setattr(
        deps_status.upgrade_planner, "generate_plan", _fake_generate_plan
    )

    contract_path = tmp_path / "contract.toml"
    contract_path.write_text("[contract]\nstatus='active'\n", encoding="utf-8")
    sbom_path = tmp_path / "sbom.json"
    sbom_path.write_text("{}", encoding="utf-8")

    settings = deps_status.PlannerSettings(
        enabled=True,
        packages=("fastapi",),
        allow_major=True,
        limit=3,
        skip_resolver=False,
        poetry="poetry",
        project_root=tmp_path,
    )

    status = deps_status.generate_status(
        preflight=None,
        renovate=None,
        cve=None,
        contract=contract_path,
        sbom=sbom_path,
        metadata=None,
        sbom_max_age_days=None,
        fail_threshold="needs-review",
        planner_settings=settings,
    )

    assert status.exit_code == 0
    assert status.guard.exit_code == 0
    assert status.guard.markdown == "Guard markdown"
    assert status.summary["recommended_commands"] == ["poetry update fastapi"]
    assert status.summary["planner_exit_code"] == 0
    assert status.summary["highest_severity"] == "ok"

    config = cast(Any, captured_config["config"])
    assert config.allow_major is True
    assert config.skip_resolver is False
    assert config.packages == frozenset({"fastapi"})


def test_generate_status_handles_disabled_planner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary_payload = {
        "summary": {
            "highest_severity": "needs-review",
            "packages_flagged": 0,
            "contract_risk": "medium",
            "drift_severity": "low",
            "notes": [],
        },
        "contract": {"risk": "medium", "status": "stale"},
        "drift": {"severity": "low"},
    }

    monkeypatch.setattr(deps_status.upgrade_guard, "main", _stub_guard(summary_payload))

    def _unexpected_generate_plan(
        *_: Any, **__: Any
    ) -> None:  # pragma: no cover - defensive guard
        pytest.fail("Planner should not be invoked when disabled")

    monkeypatch.setattr(
        deps_status.upgrade_planner, "generate_plan", _unexpected_generate_plan
    )

    contract_path = tmp_path / "contract.toml"
    contract_path.write_text("[contract]\nstatus='stale'\n", encoding="utf-8")

    status = deps_status.generate_status(
        preflight=None,
        renovate=None,
        cve=None,
        contract=contract_path,
        sbom=None,
        metadata=None,
        sbom_max_age_days=None,
        fail_threshold="needs-review",
        planner_settings=deps_status.PlannerSettings(enabled=False),
    )

    assert status.planner is None
    assert status.summary["planner_reason"] == "planner skipped by configuration"
    assert status.summary["planner_exit_code"] is None
    assert status.exit_code == status.guard.exit_code


def test_cli_status_exports_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured_kwargs: dict[str, Any] = {}

    def _fake_generate_status(**kwargs) -> deps_status.DependencyStatus:
        captured_kwargs["kwargs"] = kwargs
        guard = deps_status.GuardRun(
            exit_code=0,
            assessment={
                "summary": {
                    "highest_severity": "ok",
                    "packages_flagged": 0,
                    "contract_risk": "ok",
                    "drift_severity": "none",
                    "notes": [],
                },
                "contract": {"risk": "ok", "status": "active"},
                "drift": {"severity": "none"},
            },
            markdown="Guard markdown",
        )
        summary = {
            "generated_at": datetime.now(UTC).isoformat(),
            "highest_severity": "ok",
            "packages_flagged": 0,
            "contract_risk": "ok",
            "drift_severity": "none",
            "notes": [],
            "guard_exit_code": 0,
            "planner_exit_code": None,
            "planner_summary": None,
            "planner_error": "planner skipped by test",
            "recommended_commands": [],
            "planner_reason": "planner skipped by test",
        }
        return deps_status.DependencyStatus(
            generated_at=datetime.now(UTC),
            guard=guard,
            planner=None,
            exit_code=0,
            summary=summary,
        )

    monkeypatch.setattr(deps_status, "generate_status", _fake_generate_status)

    output_path = tmp_path / "reports" / "deps.json"
    preflight_path = tmp_path / "preflight.json"

    prometheus_cli.dependency_status(
        profiles=[f"preflight={preflight_path}"],
        contract=prometheus_cli.DEFAULT_DEPENDENCY_CONTRACT,
        sbom=None,
        metadata=None,
        sbom_max_age_days=None,
        fail_threshold="needs-review",
        planner_enabled=True,
        planner_packages=None,
        planner_allow_major=False,
        planner_limit=None,
        planner_run_resolver=False,
        output_path=output_path,
        verbose=False,
    )

    captured = capsys.readouterr()
    assert "Dependency status" in captured.out
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["planner_reason"] == "planner skipped by test"

    kwargs = cast(dict[str, Any], captured_kwargs["kwargs"])
    assert kwargs["preflight"] == preflight_path
    assert kwargs["planner_settings"].enabled is True
    assert kwargs["planner_settings"].skip_resolver is True
    assert kwargs["planner_settings"].packages is None
