"""Tests for scripts/offline_package.py."""

from __future__ import annotations

import importlib
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest

from prometheus.packaging import OfflinePackagingConfig
from prometheus.packaging.offline import (
    OfflinePackagingOrchestrator as RealOrchestrator,
)
from prometheus.packaging.offline import (
    PackagingResult,
    PhaseResult,
)

MODULE_NAME = "scripts.offline_package"


class StubOrchestrator:
    """Lightweight stub used to observe CLI interactions."""

    PHASES: ClassVar[tuple[str, ...]] = RealOrchestrator.PHASES
    result: ClassVar[PackagingResult | None] = None
    last_call: ClassVar[dict[str, Any] | None] = None

    def __init__(self, *, config, repo_root: Path, dry_run: bool) -> None:
        self.config = config
        self.repo_root = repo_root
        self.dry_run = dry_run
        self.dependency_summary: dict[str, Any] = {}
        self.dependency_updates: list[dict[str, Any]] = []
        self.symlink_replacements = 0
        self.pointer_scan_paths: list[str] = []
        self.git_hooks_path: Path | None = None
        self.hook_repairs: list[str] = []
        self.hook_removals: list[str] = []
        self.wheelhouse_audit: dict[str, Any] = {
            "status": "ok",
            "wheel_count": 0,
            "requirement_count": 0,
        }
        self.preflight_report: dict[str, Any] = {"status": "not-run"}

    def run(
        self,
        *,
        only: list[str] | None = None,
        skip: list[str] | None = None,
    ) -> PackagingResult:
        type(self).last_call = {"only": only, "skip": skip}
        result = type(self).result
        assert result is not None, "StubOrchestrator.result must be set for test"
        return result


def _import_cli_module(*, reload: bool = False) -> ModuleType:
    if MODULE_NAME in sys.modules and reload:
        return importlib.reload(sys.modules[MODULE_NAME])
    if MODULE_NAME in sys.modules:
        return sys.modules[MODULE_NAME]
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[3]
        repo_str = str(repo_root)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)
        return importlib.import_module(MODULE_NAME)


def _configure_stub(
    monkeypatch: pytest.MonkeyPatch,
    cli: ModuleType,
    repo_root: Path,
) -> None:
    def fake_load_config(path: Path | None = None) -> OfflinePackagingConfig:
        config = OfflinePackagingConfig()
        config.repo_root = repo_root
        return config

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "OfflinePackagingOrchestrator", StubOrchestrator)
    StubOrchestrator.result = None
    StubOrchestrator.last_call = None


def _make_result(
    succeeded: bool, *, failed_phase: str | None = None
) -> PackagingResult:
    phases = [PhaseResult(name="cleanup", succeeded=True)]
    if failed_phase:
        phases.append(
            PhaseResult(
                name=failed_phase,
                succeeded=False,
                detail="RuntimeError: dependency failure",
            )
        )
    started = datetime.now(UTC)
    finished = datetime.now(UTC)
    return PackagingResult(
        succeeded=succeeded,
        phase_results=phases,
        started_at=started,
        finished_at=finished,
    )


def test_module_self_heals_sys_path(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    cleaned_path = [entry for entry in sys.path if Path(entry).resolve() != repo_root]
    monkeypatch.setattr(sys, "path", cleaned_path)
    for name in [MODULE_NAME, "prometheus", "prometheus.packaging"]:
        sys.modules.pop(name, None)

    cli = _import_cli_module()

    assert str(repo_root) in sys.path
    assert hasattr(cli, "OfflinePackagingOrchestrator")


def test_main_returns_zero_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cli = _import_cli_module(reload=True)
    _configure_stub(monkeypatch, cli, tmp_path)
    caplog.set_level(logging.INFO)

    StubOrchestrator.result = _make_result(True)

    exit_code = cli.main(
        [
            "--repo-root",
            str(tmp_path),
            "--only-phase",
            "cleanup",
        ]
    )

    assert exit_code == 0
    assert StubOrchestrator.last_call == {"only": ["cleanup"], "skip": None}
    assert any(
        "Offline packaging completed successfully" in record.message
        for record in caplog.records
    )
    assert any("Dependency preflight" in record.message for record in caplog.records)


def test_main_returns_one_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cli = _import_cli_module(reload=True)
    _configure_stub(monkeypatch, cli, tmp_path)
    caplog.set_level(logging.INFO)

    StubOrchestrator.result = _make_result(False, failed_phase="dependencies")

    exit_code = cli.main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-phase",
            "git",
        ]
    )

    assert exit_code == 1
    assert StubOrchestrator.last_call == {"only": None, "skip": ["git"]}
    assert any(
        record.levelno >= logging.ERROR
        and "Offline packaging failed during dependencies" in record.message
        for record in caplog.records
    )
