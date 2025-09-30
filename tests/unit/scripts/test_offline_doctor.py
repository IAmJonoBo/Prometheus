"""Tests for scripts/offline_doctor.py."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.offline_doctor import (
    _format_examples,
    _render_diagnostics,
    _render_table,
    build_parser,
    main,
)


def test_build_parser_creates_expected_arguments() -> None:
    """Test that the argument parser is created with expected arguments."""
    parser = build_parser()
    args = parser.parse_args([])
    
    # Check defaults
    assert args.format == "text"
    assert args.json is False
    assert args.verbose is False
    
    # Test format options
    args = parser.parse_args(["--format", "json"])
    assert args.format == "json"
    
    args = parser.parse_args(["--format", "table"])
    assert args.format == "table"
    
    args = parser.parse_args(["--format", "text"])
    assert args.format == "text"
    
    # Test backward compatibility with --json
    args = parser.parse_args(["--json"])
    assert args.json is True


def test_format_examples_truncates_long_lists() -> None:
    """Test that _format_examples truncates long lists."""
    values = ["item1", "item2", "item3", "item4", "item5", "item6", "item7"]
    result = _format_examples(values)
    assert "item1" in result
    assert "item5" in result
    assert "item7" not in result
    assert "…" in result
    
    # Short lists are not truncated
    short_values = ["item1", "item2", "item3"]
    result = _format_examples(short_values)
    assert "item1" in result
    assert "item3" in result
    assert "…" not in result


def test_render_diagnostics_text_format(monkeypatch, capsys) -> None:
    """Test text format rendering."""
    diagnostics = {
        "repo_root": "/test/repo",
        "config_path": "/test/config.toml",
        "python": {"status": "ok", "version": "3.12.0"},
        "pip": {"status": "ok", "version": "25.0"},
        "poetry": {"status": "ok", "version": "1.8.3"},
        "docker": {"status": "skipped"},
        "wheelhouse": {"status": "ok"},
    }
    
    import logging
    logging.basicConfig(level=logging.INFO)
    
    _render_diagnostics(diagnostics)
    captured = capsys.readouterr()
    
    assert "Python status: ok" in captured.err
    assert "Pip version: 25.0" in captured.err


def test_render_table_shows_all_sections(capsys) -> None:
    """Test that table format shows all diagnostic sections."""
    diagnostics = {
        "repo_root": "/test/repo",
        "config_path": "/test/config.toml",
        "generated_at": "2025-09-30T12:00:00Z",
        "python": {"status": "ok", "version": "3.12.0"},
        "pip": {"status": "ok", "version": "25.0"},
        "poetry": {"status": "ok", "version": "1.8.3"},
        "docker": {"status": "ok", "version": "28.0.4"},
        "git": {
            "status": "ok",
            "branch": "main",
            "commit": "abc123de",
            "uncommitted_changes": 0,
            "lfs_available": True,
            "lfs_tracked_files": 5,
        },
        "disk_space": {
            "status": "ok",
            "total_gb": 100.0,
            "used_gb": 50.0,
            "free_gb": 50.0,
            "percent_used": 50.0,
        },
        "build_artifacts": {
            "status": "ok",
            "dist_exists": True,
            "wheels_in_dist": 1,
            "wheelhouse_exists": True,
            "wheels_in_wheelhouse": 10,
            "manifest_exists": True,
            "requirements_exists": True,
        },
        "dependencies": {
            "status": "ok",
            "pyproject_exists": True,
            "poetry_lock_exists": True,
            "lock_age_days": 5.0,
        },
        "wheelhouse": {"status": "ok"},
    }
    
    _render_table(diagnostics)
    captured = capsys.readouterr()
    
    # Check that all sections are present
    assert "Offline Packaging Diagnostic Report" in captured.out
    assert "Repository: /test/repo" in captured.out
    assert "python" in captured.out
    assert "pip" in captured.out
    assert "poetry" in captured.out
    assert "docker" in captured.out
    assert "Git Repository:" in captured.out
    assert "Branch:    main" in captured.out
    assert "Disk Space:" in captured.out
    assert "Build Artifacts:" in captured.out
    assert "Dependencies:" in captured.out
    assert "ALL CHECKS PASSED" in captured.out


def test_render_table_shows_errors(capsys) -> None:
    """Test that table format correctly shows errors."""
    diagnostics = {
        "repo_root": "/test/repo",
        "config_path": None,
        "generated_at": "2025-09-30T12:00:00Z",
        "python": {"status": "ok"},
        "pip": {"status": "error", "message": "pip not found"},
        "poetry": {"status": "ok"},
        "docker": {"status": "skipped"},
        "git": {"status": "ok"},
        "disk_space": {"status": "ok"},
        "build_artifacts": {"status": "ok"},
        "dependencies": {"status": "ok"},
        "wheelhouse": {"status": "ok"},
    }
    
    _render_table(diagnostics)
    captured = capsys.readouterr()
    
    assert "ERRORS DETECTED" in captured.out
    assert "✗" in captured.out


def test_render_table_shows_warnings(capsys) -> None:
    """Test that table format correctly shows warnings."""
    diagnostics = {
        "repo_root": "/test/repo",
        "config_path": None,
        "generated_at": "2025-09-30T12:00:00Z",
        "python": {"status": "ok"},
        "pip": {"status": "ok"},
        "poetry": {"status": "warning", "message": "old version"},
        "docker": {"status": "skipped"},
        "git": {"status": "ok"},
        "disk_space": {"status": "ok"},
        "build_artifacts": {"status": "ok"},
        "dependencies": {"status": "ok"},
        "wheelhouse": {"status": "ok"},
    }
    
    _render_table(diagnostics)
    captured = capsys.readouterr()
    
    assert "WARNINGS DETECTED" in captured.out
    assert "⚠" in captured.out


def test_main_json_format(monkeypatch, tmp_path: Path, capsys) -> None:
    """Test main() with JSON format."""
    # Create a minimal repo structure
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "poetry.lock").write_text("")
    vendor_wheelhouse = tmp_path / "vendor" / "wheelhouse"
    vendor_wheelhouse.mkdir(parents=True)
    (vendor_wheelhouse / "requirements.txt").write_text("")
    
    # Mock the orchestrator
    mock_diagnostics = {
        "python": {"status": "ok"},
        "pip": {"status": "ok"},
        "poetry": {"status": "ok"},
        "docker": {"status": "skipped"},
        "git": {"status": "ok"},
        "disk_space": {"status": "ok"},
        "build_artifacts": {"status": "ok"},
        "dependencies": {"status": "ok"},
        "wheelhouse": {"status": "ok"},
    }
    
    def mock_doctor(self):
        return mock_diagnostics
    
    from prometheus.packaging.offline import OfflinePackagingOrchestrator
    monkeypatch.setattr(OfflinePackagingOrchestrator, "doctor", mock_doctor)
    
    # Run with JSON format
    exit_code = main(["--format", "json", "--repo-root", str(tmp_path)])
    
    assert exit_code == 0
    captured = capsys.readouterr()
    
    # Should output valid JSON
    result = json.loads(captured.out)
    assert result["python"]["status"] == "ok"


def test_main_table_format(monkeypatch, tmp_path: Path, capsys) -> None:
    """Test main() with table format."""
    # Create a minimal repo structure
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "poetry.lock").write_text("")
    vendor_wheelhouse = tmp_path / "vendor" / "wheelhouse"
    vendor_wheelhouse.mkdir(parents=True)
    (vendor_wheelhouse / "requirements.txt").write_text("")
    
    # Mock the orchestrator
    mock_diagnostics = {
        "repo_root": str(tmp_path),
        "config_path": None,
        "generated_at": "2025-09-30T12:00:00Z",
        "python": {"status": "ok"},
        "pip": {"status": "ok"},
        "poetry": {"status": "ok"},
        "docker": {"status": "skipped"},
        "git": {"status": "ok"},
        "disk_space": {"status": "ok"},
        "build_artifacts": {"status": "ok"},
        "dependencies": {"status": "ok"},
        "wheelhouse": {"status": "ok"},
    }
    
    def mock_doctor(self):
        return mock_diagnostics
    
    from prometheus.packaging.offline import OfflinePackagingOrchestrator
    monkeypatch.setattr(OfflinePackagingOrchestrator, "doctor", mock_doctor)
    
    # Run with table format
    exit_code = main(["--format", "table", "--repo-root", str(tmp_path)])
    
    assert exit_code == 0
    captured = capsys.readouterr()
    
    assert "Offline Packaging Diagnostic Report" in captured.out
    assert "ALL CHECKS PASSED" in captured.out


def test_main_backward_compatible_json_flag(monkeypatch, tmp_path: Path, capsys) -> None:
    """Test that --json flag still works for backward compatibility."""
    # Create a minimal repo structure
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "poetry.lock").write_text("")
    vendor_wheelhouse = tmp_path / "vendor" / "wheelhouse"
    vendor_wheelhouse.mkdir(parents=True)
    (vendor_wheelhouse / "requirements.txt").write_text("")
    
    # Mock the orchestrator
    mock_diagnostics = {
        "python": {"status": "ok"},
        "pip": {"status": "ok"},
        "poetry": {"status": "ok"},
        "docker": {"status": "skipped"},
        "git": {"status": "ok"},
        "disk_space": {"status": "ok"},
        "build_artifacts": {"status": "ok"},
        "dependencies": {"status": "ok"},
        "wheelhouse": {"status": "ok"},
    }
    
    def mock_doctor(self):
        return mock_diagnostics
    
    from prometheus.packaging.offline import OfflinePackagingOrchestrator
    monkeypatch.setattr(OfflinePackagingOrchestrator, "doctor", mock_doctor)
    
    # Run with --json flag (backward compatibility)
    exit_code = main(["--json", "--repo-root", str(tmp_path)])
    
    assert exit_code == 0
    captured = capsys.readouterr()
    
    # Should output valid JSON
    result = json.loads(captured.out)
    assert result["python"]["status"] == "ok"
