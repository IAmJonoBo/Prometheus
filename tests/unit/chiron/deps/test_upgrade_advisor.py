"""Tests for intelligent upgrade advisor."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from chiron.deps import drift as dependency_drift
from chiron.deps.upgrade_advisor import (
    UpgradeAdvisor,
    UpgradeRecommendation,
    generate_upgrade_advice,
)


@pytest.fixture
def sample_drift_packages():
    """Sample drift packages for testing."""
    return [
        dependency_drift.PackageDrift(
            name="requests",
            current="2.28.0",
            latest="2.31.0",
            severity=dependency_drift.RISK_MINOR,
            notes=["Minor version update with new features"],
        ),
        dependency_drift.PackageDrift(
            name="urllib3",
            current="1.26.0",
            latest="1.26.18",
            severity=dependency_drift.RISK_PATCH,
            notes=["Security patch - CVE-2023-xxxxx"],
        ),
        dependency_drift.PackageDrift(
            name="django",
            current="3.2.0",
            latest="4.2.0",
            severity=dependency_drift.RISK_MAJOR,
            notes=["Major version upgrade with breaking changes"],
        ),
    ]


def test_advisor_initialization():
    """Test advisor can be initialized."""
    advisor = UpgradeAdvisor(
        mirror_root=Path("/tmp/mirror"),
        conservative=True,
        security_first=True,
    )
    assert advisor.conservative is True
    assert advisor.security_first is True


def test_generate_advice_basic(sample_drift_packages):
    """Test basic advice generation."""
    advice = generate_upgrade_advice(
        sample_drift_packages,
        metadata={},
        conservative=True,
        security_first=True,
    )
    
    assert advice is not None
    assert len(advice.recommendations) == 3
    assert advice.summary["total"] == 3


def test_priority_assignment(sample_drift_packages):
    """Test priority is correctly assigned."""
    advice = generate_upgrade_advice(
        sample_drift_packages,
        metadata={},
        security_first=True,
    )
    
    # Find security-related package
    urllib3_rec = next(
        (r for r in advice.recommendations if r.package == "urllib3"),
        None,
    )
    assert urllib3_rec is not None
    assert urllib3_rec.priority == "critical"  # Security update
    
    # Find minor version package
    requests_rec = next(
        (r for r in advice.recommendations if r.package == "requests"),
        None,
    )
    assert requests_rec is not None
    assert requests_rec.priority == "medium"


def test_auto_apply_safe_detection(sample_drift_packages):
    """Test safe auto-apply detection."""
    advice = generate_upgrade_advice(
        sample_drift_packages,
        metadata={},
        conservative=True,
    )
    
    # Major versions should NOT be safe to auto-apply
    django_rec = next(
        (r for r in advice.recommendations if r.package == "django"),
        None,
    )
    assert django_rec is not None
    assert django_rec.auto_apply_safe is False


def test_confidence_calculation():
    """Test confidence scoring."""
    advisor = UpgradeAdvisor(conservative=True)
    
    # Create patch-level drift
    patch_drift = dependency_drift.PackageDrift(
        name="test-pkg",
        current="1.0.0",
        latest="1.0.1",
        severity=dependency_drift.RISK_PATCH,
        notes=[],
    )
    
    recommendation = advisor._analyze_package(patch_drift, {})
    assert recommendation is not None
    assert recommendation.confidence >= 0.5


def test_advice_serialization(sample_drift_packages):
    """Test advice can be serialized to dict."""
    advice = generate_upgrade_advice(
        sample_drift_packages,
        metadata={},
    )
    
    advice_dict = advice.to_dict()
    assert "generated_at" in advice_dict
    assert "recommendations" in advice_dict
    assert "summary" in advice_dict
    assert len(advice_dict["recommendations"]) == 3


def test_empty_package_list():
    """Test with empty package list."""
    advice = generate_upgrade_advice([], metadata={})
    
    assert advice is not None
    assert len(advice.recommendations) == 0
    assert advice.summary["total"] == 0
