from __future__ import annotations

from collections.abc import Sequence

import pytest
from typer.testing import CliRunner

from prometheus.cli import app


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_deps_guard_forwards_arguments(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    captured: list[Sequence[str] | None] = []

    def fake_main(argv: Sequence[str] | None) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr("prometheus.cli.upgrade_guard.main", fake_main)

    result = runner.invoke(app, ["deps", "guard", "--contract", "foo.toml"])

    assert result.exit_code == 0
    assert captured == [["--contract", "foo.toml"]]


def test_deps_guard_propagates_exit(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    def fake_main(argv: Sequence[str] | None) -> int:
        return 17

    monkeypatch.setattr("prometheus.cli.upgrade_guard.main", fake_main)

    result = runner.invoke(app, ["deps", "guard"])

    assert result.exit_code == 17


def test_deps_drift_forwards_arguments(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    captured: list[Sequence[str] | None] = []

    def fake_main(argv: Sequence[str] | None) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr("prometheus.cli.dependency_drift.main", fake_main)

    result = runner.invoke(app, ["deps", "drift", "--sbom", "var/sbom.json"])

    assert result.exit_code == 0
    assert captured == [["--sbom", "var/sbom.json"]]


def test_deps_sync_proxies_to_runner(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    captured: list[Sequence[str] | None] = []

    def fake_run(argv: Sequence[str] | None) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr("prometheus.cli._run_sync_dependencies", fake_run)

    result = runner.invoke(app, ["deps", "sync", "--apply"])

    assert result.exit_code == 0
    assert captured == [["--apply"]]


def test_deps_sync_without_arguments(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    captured: list[Sequence[str] | None] = []

    def fake_run(argv: Sequence[str] | None) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr("prometheus.cli._run_sync_dependencies", fake_run)

    result = runner.invoke(app, ["deps", "sync"])

    assert result.exit_code == 0
    assert captured == [None]


def test_remediation_wheelhouse_forwards_arguments(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    captured: list[Sequence[str] | None] = []

    def fake_main(argv: Sequence[str] | None) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr("prometheus.cli.remediation_cli.main", fake_main)

    result = runner.invoke(
        app,
        [
            "remediation",
            "wheelhouse",
            "--log",
            "wheelhouse.log",
            "--output",
            "summary.json",
        ],
    )

    assert result.exit_code == 0
    assert captured == [
        ["wheelhouse", "--log", "wheelhouse.log", "--output", "summary.json"]
    ]


def test_remediation_runtime_propagates_exit(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    def fake_main(argv: Sequence[str] | None) -> int:
        assert argv == ["runtime", "--from", "report.json"]
        return 3

    monkeypatch.setattr("prometheus.cli.remediation_cli.main", fake_main)

    result = runner.invoke(app, ["remediation", "runtime", "--from", "report.json"])

    assert result.exit_code == 3
