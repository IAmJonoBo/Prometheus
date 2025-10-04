#!/usr/bin/env python3
"""Tests for automated dependency synchronization."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from chiron.orchestration.auto_sync import (
    AutoSyncConfig,
    AutoSyncOrchestrator,
    AutoSyncResult,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock orchestration coordinator."""
    coordinator = Mock()
    coordinator.deps_preflight = Mock(return_value={"status": "ok"})
    coordinator.deps_guard = Mock(
        return_value={"status": "safe", "flagged_packages": []}
    )
    coordinator.deps_upgrade = Mock(return_value={"success": True})
    coordinator.deps_sync = Mock(return_value=True)
    return coordinator


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create temporary state directory."""
    state_dir = tmp_path / "var"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def test_auto_sync_config_defaults():
    """Test default configuration values."""
    config = AutoSyncConfig()

    assert config.auto_upgrade is True
    assert config.auto_apply_safe is True
    assert config.force_sync is False
    assert config.update_mirror is True
    assert config.max_major_updates == 0
    assert config.max_minor_updates == 5
    assert config.max_patch_updates == 20
    assert config.enable_rollback is True
    assert config.sync_dev_env is True
    assert config.sync_prod_env is False


def test_auto_sync_config_custom():
    """Test custom configuration."""
    config = AutoSyncConfig(
        auto_upgrade=False,
        auto_apply_safe=False,
        enable_rollback=False,
        sync_prod_env=True,
    )

    assert config.auto_upgrade is False
    assert config.auto_apply_safe is False
    assert config.enable_rollback is False
    assert config.sync_prod_env is True


def test_auto_sync_result_to_dict():
    """Test AutoSyncResult serialization."""
    result = AutoSyncResult(
        success=True,
        stages_completed=["snapshot", "assessment"],
        updates_applied=[{"package": "test"}],
        errors=[],
    )

    data = result.to_dict()

    assert data["success"] is True
    assert "timestamp" in data
    assert data["stages_completed"] == ["snapshot", "assessment"]
    assert data["updates_applied"] == [{"package": "test"}]
    assert data["errors"] == []
    assert data["rollback_performed"] is False


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_auto_sync_orchestrator_init(mock_repo_root, mock_var_root, tmp_path):
    """Test orchestrator initialization."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    config = AutoSyncConfig(dry_run=True, verbose=True)
    orchestrator = AutoSyncOrchestrator(config)

    assert orchestrator.config.dry_run is True
    assert orchestrator.config.verbose is True
    assert orchestrator.coordinator is not None


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_create_snapshot(mock_repo_root, mock_var_root, tmp_path, mock_coordinator):
    """Test snapshot creation."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    # Create dummy files
    (tmp_path / "poetry.lock").write_text("lock content")
    (tmp_path / "pyproject.toml").write_text("project content")
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "dependency-profile.toml").write_text("profile content")

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=mock_coordinator,
    )

    snapshot = orchestrator._create_snapshot()

    assert "timestamp" in snapshot
    assert "lock_file_hash" in snapshot
    assert "pyproject_hash" in snapshot
    assert "contract_hash" in snapshot


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_assess_updates_safe(mock_repo_root, mock_var_root, tmp_path, mock_coordinator):
    """Test update assessment when status is safe."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=mock_coordinator,
    )

    assessment = orchestrator._assess_updates()

    assert assessment["safe"] is True
    assert assessment["blocked"] is False
    assert assessment["flagged_count"] == 0
    assert assessment["guard_status"] == "safe"


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_assess_updates_blocked(mock_repo_root, mock_var_root, tmp_path):
    """Test update assessment when status is blocked."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    coordinator = Mock()
    coordinator.deps_preflight = Mock(return_value={"status": "ok"})
    coordinator.deps_guard = Mock(
        return_value={
            "status": "blocked",
            "flagged_packages": [{"name": "vulnerable-pkg"}],
        }
    )

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=coordinator,
    )

    assessment = orchestrator._assess_updates()

    assert assessment["safe"] is False
    assert assessment["blocked"] is True
    assert assessment["flagged_count"] == 1
    assert assessment["guard_status"] == "blocked"


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_apply_safe_updates_disabled(
    mock_repo_root, mock_var_root, tmp_path, mock_coordinator
):
    """Test safe update application when disabled."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    config = AutoSyncConfig(auto_apply_safe=False)
    orchestrator = AutoSyncOrchestrator(
        config=config,
        coordinator=mock_coordinator,
    )

    assessment = {"safe": True, "blocked": False}
    result = orchestrator._apply_safe_updates(assessment)

    assert result["applied"] is False
    assert result["reason"] == "auto_apply_safe disabled"


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_apply_safe_updates_blocked(
    mock_repo_root, mock_var_root, tmp_path, mock_coordinator
):
    """Test safe update application when blocked."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=mock_coordinator,
    )

    assessment = {"safe": False, "blocked": True}
    result = orchestrator._apply_safe_updates(assessment)

    assert result["applied"] is False
    assert result["reason"] == "blocked by guard"


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_apply_safe_updates_success(
    mock_repo_root, mock_var_root, tmp_path, mock_coordinator
):
    """Test successful safe update application."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=mock_coordinator,
    )

    assessment = {"safe": True, "blocked": False}
    result = orchestrator._apply_safe_updates(assessment)

    assert result["applied"] is True
    mock_coordinator.deps_upgrade.assert_called_once()


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_sync_environments_dev_only(
    mock_repo_root, mock_var_root, tmp_path, mock_coordinator
):
    """Test environment synchronization for dev only."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    config = AutoSyncConfig(sync_dev_env=True, sync_prod_env=False)
    orchestrator = AutoSyncOrchestrator(
        config=config,
        coordinator=mock_coordinator,
    )

    result = orchestrator._sync_environments()

    assert "dev" in result
    assert "prod" not in result
    mock_coordinator.deps_sync.assert_called_once()


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_sync_environments_both(
    mock_repo_root, mock_var_root, tmp_path, mock_coordinator
):
    """Test environment synchronization for both dev and prod."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    config = AutoSyncConfig(sync_dev_env=True, sync_prod_env=True)
    orchestrator = AutoSyncOrchestrator(
        config=config,
        coordinator=mock_coordinator,
    )

    result = orchestrator._sync_environments()

    assert "dev" in result
    assert "prod" in result
    assert mock_coordinator.deps_sync.call_count == 2


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_validate_sync(mock_repo_root, mock_var_root, tmp_path, mock_coordinator):
    """Test validation after sync."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=mock_coordinator,
    )

    result = orchestrator._validate_sync()

    assert result["validated"] is True
    assert result["status"] == "safe"
    mock_coordinator.deps_preflight.assert_called_once()
    mock_coordinator.deps_guard.assert_called_once()


@patch("chiron.orchestration.auto_sync.subprocess.run")
@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_rollback_success(
    mock_repo_root, mock_var_root, mock_subprocess, tmp_path, mock_coordinator
):
    """Test successful rollback."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    # Create snapshot file
    snapshot_file = tmp_path / "auto-sync-snapshot.json"
    snapshot_file.write_text(json.dumps({"timestamp": "2024-01-01"}))

    mock_subprocess.return_value = Mock(returncode=0)

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=mock_coordinator,
    )
    orchestrator._snapshot_file = snapshot_file

    result = orchestrator._rollback()

    assert result is True
    mock_subprocess.assert_called_once()


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_rollback_disabled(
    mock_repo_root, mock_var_root, tmp_path, mock_coordinator
):
    """Test rollback when disabled."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    config = AutoSyncConfig(enable_rollback=False)
    orchestrator = AutoSyncOrchestrator(
        config=config,
        coordinator=mock_coordinator,
    )

    result = orchestrator._rollback()

    assert result is False


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_execute_success_flow(mock_repo_root, mock_var_root, tmp_path):
    """Test successful execution flow."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    # Create dummy files
    (tmp_path / "poetry.lock").write_text("lock")
    (tmp_path / "pyproject.toml").write_text("project")
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "dependency-profile.toml").write_text("profile")

    coordinator = Mock()
    coordinator.deps_preflight = Mock(return_value={"status": "ok"})
    coordinator.deps_guard = Mock(
        return_value={"status": "safe", "flagged_packages": []}
    )
    coordinator.deps_upgrade = Mock(return_value={"success": True})
    coordinator.deps_sync = Mock(return_value=True)

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=coordinator,
    )

    result = orchestrator.execute()

    assert result.success is True
    assert len(result.stages_completed) == 5
    assert len(result.errors) == 0
    assert result.rollback_performed is False


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_execute_blocked_flow(mock_repo_root, mock_var_root, tmp_path):
    """Test execution flow when updates are blocked."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    # Create dummy files
    (tmp_path / "poetry.lock").write_text("lock")
    (tmp_path / "pyproject.toml").write_text("project")
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "dependency-profile.toml").write_text("profile")

    coordinator = Mock()
    coordinator.deps_preflight = Mock(return_value={"status": "ok"})
    coordinator.deps_guard = Mock(
        return_value={"status": "blocked", "flagged_packages": [{"name": "vuln"}]}
    )

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=coordinator,
    )

    result = orchestrator.execute()

    assert result.success is False
    assert "blocked" in result.errors[0]
    assert "assessment" in result.stages_completed


@patch("chiron.orchestration.auto_sync.VAR_ROOT")
@patch("chiron.orchestration.auto_sync.REPO_ROOT")
def test_get_status(mock_repo_root, mock_var_root, tmp_path, mock_coordinator):
    """Test status retrieval."""
    mock_var_root.__truediv__ = lambda self, x: tmp_path / x
    mock_repo_root.__truediv__ = lambda self, x: tmp_path / x

    # Create state file
    state_file = tmp_path / "auto-sync-state.json"
    state_data = {"success": True, "timestamp": "2024-01-01"}
    state_file.write_text(json.dumps(state_data))

    orchestrator = AutoSyncOrchestrator(
        config=AutoSyncConfig(),
        coordinator=mock_coordinator,
    )

    status = orchestrator.get_status()

    assert "config" in status
    assert "last_run" in status
    assert status["config"]["auto_upgrade"] is True
    assert status["config"]["enable_rollback"] is True
