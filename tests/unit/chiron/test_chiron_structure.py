"""Basic import and structure tests for Chiron subsystem."""

from __future__ import annotations

import pytest


def test_chiron_imports():
    """Test that all chiron modules can be imported."""
    import chiron
    import chiron.deps
    import chiron.doctor
    import chiron.orchestration
    import chiron.packaging
    import chiron.remediation
    import chiron.tools
    
    assert chiron.__version__ == "0.1.0"


def test_chiron_deps_modules():
    """Test chiron.deps submodules are accessible."""
    from chiron.deps import status, guard, planner, drift, sync, preflight
    from chiron.deps import graph, preflight_summary, verify, mirror_manager
    
    assert hasattr(status, 'generate_status')
    assert hasattr(guard, 'main')
    assert hasattr(planner, 'main')
    assert hasattr(drift, 'main')
    assert hasattr(sync, 'main')
    assert hasattr(preflight, 'main')


def test_chiron_doctor_modules():
    """Test chiron.doctor submodules are accessible."""
    from chiron.doctor import offline, package_cli, bootstrap, models
    
    assert hasattr(offline, 'main')
    assert hasattr(package_cli, 'main')
    assert hasattr(bootstrap, 'main')
    assert hasattr(models, 'main')


def test_chiron_tools_modules():
    """Test chiron.tools submodules are accessible."""
    from chiron.tools import format_yaml
    
    assert hasattr(format_yaml, 'main')


def test_chiron_orchestration_modules():
    """Test chiron.orchestration submodules are accessible."""
    from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
    from chiron.orchestration import governance
    
    assert OrchestrationCoordinator is not None
    assert OrchestrationContext is not None
