"""Integration tests for Chiron frontier standards features."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chiron.github.sync import GitHubArtifactSync, SyncResult
from chiron.remediation.autoremediate import (
    AutoRemediator,
    RemediationAction,
    RemediationResult,
)


class TestGitHubArtifactSync:
    """Test GitHub artifact synchronization."""
    
    def test_github_artifact_sync_initialization(self):
        """Test GitHubArtifactSync initializes correctly."""
        syncer = GitHubArtifactSync(
            repo="test/repo",
            target_dir=Path("/tmp/test"),
            verbose=True,
        )
        
        assert syncer.repo == "test/repo"
        assert syncer.target_dir == Path("/tmp/test")
        assert syncer.verbose is True
    
    def test_github_artifact_sync_no_gh_cli(self, monkeypatch):
        """Test graceful handling when gh CLI is unavailable."""
        def mock_check_gh_cli(self):
            return False
        
        monkeypatch.setattr(GitHubArtifactSync, "_check_gh_cli", mock_check_gh_cli)
        
        syncer = GitHubArtifactSync()
        result = syncer.download_artifacts("12345", ["test-artifact"])
        
        assert not result.success
        assert "GitHub CLI" in result.errors[0]
    
    def test_validate_artifacts_missing_dir(self):
        """Test validation of non-existent artifact directory."""
        syncer = GitHubArtifactSync()
        validation = syncer.validate_artifacts(
            Path("/nonexistent/path"),
            "wheelhouse",
        )
        
        assert not validation["valid"]
        assert "not found" in validation["errors"][0].lower()
    
    def test_validate_artifacts_wheelhouse_structure(self, tmp_path):
        """Test validation of wheelhouse structure."""
        wheelhouse_dir = tmp_path / "wheelhouse"
        wheelhouse_dir.mkdir()
        
        # Create a test wheel file
        (wheelhouse_dir / "test-1.0.0-py3-none-any.whl").touch()
        
        # Create manifest
        manifest = {
            "wheel_count": 1,
            "timestamp": "2025-01-01T00:00:00Z",
        }
        (wheelhouse_dir / "manifest.json").write_text(json.dumps(manifest))
        
        syncer = GitHubArtifactSync()
        validation = syncer.validate_artifacts(wheelhouse_dir, "wheelhouse")
        
        assert validation["valid"]
        assert validation["metadata"]["wheels_found"] == 1
        assert validation["metadata"]["wheel_count"] == 1
    
    def test_validate_artifacts_empty_wheelhouse(self, tmp_path):
        """Test validation of empty wheelhouse."""
        wheelhouse_dir = tmp_path / "wheelhouse"
        wheelhouse_dir.mkdir()
        
        syncer = GitHubArtifactSync()
        validation = syncer.validate_artifacts(wheelhouse_dir, "wheelhouse")
        
        assert not validation["valid"]
        assert "No wheel files found" in validation["errors"]


class TestAutoRemediator:
    """Test intelligent autoremediation engine."""
    
    def test_autoremediation_initialization(self):
        """Test AutoRemediator initializes correctly."""
        remediator = AutoRemediator(dry_run=True, auto_apply=True)
        
        assert remediator.dry_run is True
        assert remediator.auto_apply is True
        assert len(remediator._action_history) == 0
    
    def test_remediate_dependency_sync_failure_poetry_lock(self):
        """Test remediation of Poetry lock issues."""
        remediator = AutoRemediator(dry_run=True)
        
        error_log = """
        Error: poetry.lock is out of date
        Run `poetry lock` to update the lock file
        """
        
        result = remediator.remediate_dependency_sync_failure(error_log)
        
        assert result.success
        assert len(result.actions_applied) > 0
        assert any("Poetry lock" in action for action in result.actions_applied)
    
    def test_remediate_dependency_sync_failure_missing_module(self):
        """Test remediation of missing module errors."""
        remediator = AutoRemediator(dry_run=True)
        
        error_log = """
        ModuleNotFoundError: No module named 'some_package'
        """
        
        result = remediator.remediate_dependency_sync_failure(error_log)
        
        assert result.success
        assert len(result.actions_applied) > 0
        assert any("dependencies" in action.lower() for action in result.actions_applied)
    
    def test_remediate_wheelhouse_failure_with_fallback(self):
        """Test wheelhouse remediation with fallback version."""
        remediator = AutoRemediator(dry_run=True)
        
        failure_summary = {
            "failures": [
                {
                    "package": "test-package",
                    "requested_version": "2.0.0",
                    "fallback_version": "1.9.0",
                },
            ],
        }
        
        result = remediator.remediate_wheelhouse_failure(failure_summary)
        
        assert result.success
        # In dry-run mode, actions are applied (logged), not warned
        assert len(result.actions_applied) > 0
        assert "test-package" in result.actions_applied[0]
    
    def test_remediate_mirror_corruption_missing_dir(self, tmp_path):
        """Test mirror remediation for missing directory."""
        remediator = AutoRemediator(dry_run=True, auto_apply=True)
        
        mirror_path = tmp_path / "nonexistent_mirror"
        result = remediator.remediate_mirror_corruption(mirror_path)
        
        assert result.success
        assert len(result.actions_applied) > 0
        assert "mirror directory" in result.actions_applied[0].lower()
    
    def test_remediate_artifact_validation_failure_no_manifest(self):
        """Test artifact remediation for missing manifest."""
        remediator = AutoRemediator(dry_run=True)
        
        validation_result = {
            "valid": False,
            "errors": ["manifest.json not found"],
        }
        
        result = remediator.remediate_artifact_validation_failure(
            validation_result,
            Path("/tmp/artifact"),
        )
        
        assert result.success
        # In dry-run mode, actions are applied (logged), not warned
        assert len(result.actions_applied) > 0
        assert "manifest" in result.actions_applied[0].lower()
    
    def test_remediate_configuration_drift(self):
        """Test drift remediation."""
        remediator = AutoRemediator(dry_run=True, auto_apply=True)
        
        drift_report = {
            "drift_count": 5,
            "drifted_packages": ["pkg1", "pkg2", "pkg3", "pkg4", "pkg5"],
        }
        
        result = remediator.remediate_configuration_drift(drift_report)
        
        assert result.success
        assert len(result.actions_applied) > 0
        assert "5 drifted" in result.actions_applied[0]
    
    def test_action_history_tracking(self):
        """Test that action history is properly tracked."""
        remediator = AutoRemediator(dry_run=True)
        
        # Run a remediation
        remediator.remediate_dependency_sync_failure("poetry.lock out of date")
        
        # Check history
        history = remediator.get_action_history()
        assert len(history) > 0
        assert all(isinstance(action, RemediationAction) for action in history)
    
    def test_confidence_based_auto_apply(self):
        """Test that confidence threshold is respected."""
        remediator = AutoRemediator(dry_run=False, auto_apply=True)
        
        # Low confidence action should be skipped
        low_confidence_action = RemediationAction(
            action_type="manual",
            description="Low confidence fix",
            confidence=0.5,
            auto_apply=False,
        )
        
        result = remediator._apply_actions([low_confidence_action])
        
        # Should be in warnings, not applied
        assert len(result.actions_applied) == 0
        assert len(result.warnings) > 0


class TestAirGappedWorkflow:
    """Test air-gapped preparation workflow integration."""
    
    def test_air_gapped_workflow_components(self):
        """Test that all components are available for air-gapped workflow."""
        from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
        
        context = OrchestrationContext(dry_run=True)
        coordinator = OrchestrationCoordinator(context)
        
        # Check that the method exists and is callable
        assert hasattr(coordinator, "air_gapped_preparation_workflow")
        assert callable(coordinator.air_gapped_preparation_workflow)
    
    def test_orchestration_context_serialization(self):
        """Test OrchestrationContext can be serialized."""
        from chiron.orchestration import OrchestrationContext
        
        context = OrchestrationContext(
            mode="local",
            dry_run=True,
            verbose=True,
        )
        
        # Test serialization
        data = context.to_dict()
        
        assert data["mode"] == "local"
        assert data["dry_run"] is True
        assert "timestamp" in data


class TestModuleExports:
    """Test that all modules properly export their APIs."""
    
    def test_github_module_exports(self):
        """Test chiron.github module exports."""
        from chiron import github
        
        assert hasattr(github, "GitHubArtifactSync")
        assert hasattr(github, "download_artifacts")
        assert hasattr(github, "validate_artifacts")
        assert hasattr(github, "sync_to_local")
    
    def test_remediation_module_has_autoremediate(self):
        """Test that autoremediate is accessible."""
        from chiron.remediation import autoremediate
        
        assert hasattr(autoremediate, "AutoRemediator")
        assert hasattr(autoremediate, "RemediationAction")
        assert hasattr(autoremediate, "RemediationResult")
    
    def test_orchestration_coordinator_has_air_gapped_workflow(self):
        """Test that air-gapped workflow is available."""
        from chiron.orchestration import OrchestrationCoordinator
        
        coordinator = OrchestrationCoordinator()
        assert hasattr(coordinator, "air_gapped_preparation_workflow")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
