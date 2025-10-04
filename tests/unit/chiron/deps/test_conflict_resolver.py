"""Tests for conflict resolver."""

from __future__ import annotations

import pytest

from chiron.deps.conflict_resolver import (
    ConflictResolver,
    DependencyConstraint,
    analyze_dependency_conflicts,
)


@pytest.fixture
def simple_dependencies():
    """Simple dependency specification."""
    return {
        "dependencies": {
            "requests": "^2.28.0",
            "urllib3": "^1.26.0",
            "certifi": ">=2022.0.0",
        },
        "dev-dependencies": {
            "pytest": "^7.0.0",
        },
    }


@pytest.fixture
def conflicting_dependencies():
    """Dependencies with version conflicts."""
    return {
        "dependencies": {
            "package-a": "^2.0.0",
            "package-b": "^1.0.0",
        },
        # Simulate transitive conflict (would need full analysis in practice)
    }


def test_resolver_initialization():
    """Test resolver can be initialized."""
    resolver = ConflictResolver(conservative=True)
    assert resolver.conservative is True


def test_analyze_simple_dependencies(simple_dependencies):
    """Test analyzing simple dependencies without conflicts."""
    report = analyze_dependency_conflicts(
        simple_dependencies,
        conservative=True,
    )
    
    assert report is not None
    assert report.summary["total_conflicts"] == 0


def test_extract_constraints(simple_dependencies):
    """Test constraint extraction."""
    resolver = ConflictResolver(conservative=True)
    constraints = resolver._extract_constraints(simple_dependencies)
    
    assert "requests" in constraints
    assert "pytest" in constraints
    assert len(constraints["requests"]) == 1
    assert constraints["requests"][0].is_direct is True


def test_constraint_serialization():
    """Test constraint can be serialized."""
    constraint = DependencyConstraint(
        package="test-pkg",
        constraint="^1.0.0",
        required_by="root",
        is_direct=True,
    )
    
    constraint_dict = constraint.to_dict()
    assert constraint_dict["package"] == "test-pkg"
    assert constraint_dict["constraint"] == "^1.0.0"


def test_report_serialization(simple_dependencies):
    """Test report can be serialized."""
    report = analyze_dependency_conflicts(simple_dependencies)
    
    report_dict = report.to_dict()
    assert "generated_at" in report_dict
    assert "conflicts" in report_dict
    assert "summary" in report_dict


def test_no_conflicts_analysis():
    """Test analysis with no conflicts."""
    deps = {
        "dependencies": {
            "single-package": "^1.0.0",
        },
    }
    
    report = analyze_dependency_conflicts(deps)
    assert report.summary["total_conflicts"] == 0
    assert report.auto_resolvable_count == 0
