"""Tests for security overlay management."""

from pathlib import Path
from unittest.mock import Mock, patch
import json

import pytest

from chiron.deps.security_overlay import (
    CVERecord,
    SecurityConstraint,
    SecurityOverlayManager,
    Severity,
)


@pytest.fixture
def osv_scan_data():
    """Create sample OSV scan data."""
    return {
        "results": [
            {
                "packages": [
                    {
                        "package": {"name": "requests"},
                        "vulnerabilities": [
                            {
                                "id": "CVE-2023-1234",
                                "summary": "Security vulnerability in requests",
                                "published": "2023-01-01T00:00:00Z",
                                "affected": [
                                    {
                                        "ranges": [
                                            {
                                                "events": [
                                                    {"introduced": "2.0.0"},
                                                    {"fixed": "2.31.0"},
                                                ]
                                            }
                                        ]
                                    }
                                ],
                                "database_specific": {
                                    "severity": [
                                        {"type": "CVSS_V3", "score": "9.1"}
                                    ]
                                },
                                "references": [
                                    {"url": "https://example.com/cve"}
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
    }


@pytest.fixture
def overlay_file(tmp_path, osv_scan_data):
    """Create a test overlay file."""
    overlay = tmp_path / "security-overlay.json"
    
    # Import from OSV data
    osv_file = tmp_path / "osv-scan.json"
    osv_file.write_text(json.dumps(osv_scan_data))
    
    manager = SecurityOverlayManager(overlay_file=overlay)
    manager.import_osv_scan(osv_file)
    
    return overlay


def test_severity_enum():
    """Test Severity enum."""
    assert Severity.CRITICAL.value == "critical"
    assert Severity.HIGH.value == "high"
    assert Severity.MEDIUM.value == "medium"
    assert Severity.LOW.value == "low"
    assert Severity.UNKNOWN.value == "unknown"


def test_severity_from_string():
    """Test converting string to Severity."""
    assert Severity.from_string("critical") == Severity.CRITICAL
    assert Severity.from_string("HIGH") == Severity.HIGH
    assert Severity.from_string("invalid") == Severity.UNKNOWN


def test_cve_record_dataclass():
    """Test CVERecord dataclass."""
    cve = CVERecord(
        cve_id="CVE-2023-1234",
        package="requests",
        affected_versions=[">=2.0.0", "<2.31.0"],
        fixed_version="2.31.0",
        severity=Severity.CRITICAL,
        description="Test vulnerability",
    )
    
    assert cve.cve_id == "CVE-2023-1234"
    assert cve.package == "requests"
    assert cve.severity == Severity.CRITICAL


def test_security_constraint_dataclass():
    """Test SecurityConstraint dataclass."""
    constraint = SecurityConstraint(
        package="requests",
        min_version="2.31.0",
        max_version="<3.0",
        reason="Security fix",
        cve_ids=["CVE-2023-1234"],
    )
    
    assert constraint.package == "requests"
    assert constraint.min_version == "2.31.0"
    assert "CVE-2023-1234" in constraint.cve_ids


def test_overlay_manager_init(tmp_path):
    """Test SecurityOverlayManager initialization."""
    overlay_file = tmp_path / "overlay.json"
    manager = SecurityOverlayManager(overlay_file=overlay_file)
    
    assert manager.overlay_file == overlay_file
    assert isinstance(manager.constraints, dict)
    assert isinstance(manager.cve_database, dict)


def test_import_osv_scan(tmp_path, osv_scan_data):
    """Test importing CVEs from OSV scan."""
    osv_file = tmp_path / "osv-scan.json"
    osv_file.write_text(json.dumps(osv_scan_data))
    
    overlay_file = tmp_path / "overlay.json"
    manager = SecurityOverlayManager(overlay_file=overlay_file)
    
    count = manager.import_osv_scan(osv_file)
    
    assert count == 1
    assert "CVE-2023-1234" in manager.cve_database
    assert "requests" in manager.constraints


def test_save_and_load_overlay(tmp_path, osv_scan_data):
    """Test saving and loading overlay."""
    osv_file = tmp_path / "osv-scan.json"
    osv_file.write_text(json.dumps(osv_scan_data))
    
    overlay_file = tmp_path / "overlay.json"
    
    # Create and save
    manager1 = SecurityOverlayManager(overlay_file=overlay_file)
    manager1.import_osv_scan(osv_file)
    manager1.save_overlay()
    
    assert overlay_file.exists()
    
    # Load
    manager2 = SecurityOverlayManager(overlay_file=overlay_file)
    
    assert len(manager2.constraints) == len(manager1.constraints)
    assert len(manager2.cve_database) == len(manager1.cve_database)


def test_generate_constraints_file(overlay_file, tmp_path):
    """Test generating pip constraints file."""
    manager = SecurityOverlayManager(overlay_file=overlay_file)
    
    output_file = tmp_path / "constraints.txt"
    manager.generate_constraints_file(output_file)
    
    assert output_file.exists()
    
    content = output_file.read_text()
    assert "requests" in content
    assert ">=" in content


def test_check_package_version_safe(overlay_file):
    """Test checking a safe package version."""
    manager = SecurityOverlayManager(overlay_file=overlay_file)
    
    is_safe, violations = manager.check_package_version("requests", "2.31.0")
    
    assert is_safe is True
    assert len(violations) == 0


def test_check_package_version_unsafe(overlay_file):
    """Test checking an unsafe package version."""
    manager = SecurityOverlayManager(overlay_file=overlay_file)
    
    is_safe, violations = manager.check_package_version("requests", "2.20.0")
    
    assert is_safe is False
    assert len(violations) > 0


def test_check_package_version_no_constraint(overlay_file):
    """Test checking package with no constraint."""
    manager = SecurityOverlayManager(overlay_file=overlay_file)
    
    is_safe, violations = manager.check_package_version("unknown-package", "1.0.0")
    
    assert is_safe is True
    assert len(violations) == 0


def test_get_recommendations(overlay_file):
    """Test getting version recommendations."""
    manager = SecurityOverlayManager(overlay_file=overlay_file)
    
    recommendations = manager.get_recommendations("requests")
    
    assert len(recommendations) > 0
    assert any("Minimum safe version" in rec for rec in recommendations)


def test_compare_versions():
    """Test version comparison."""
    manager = SecurityOverlayManager()
    
    assert manager._compare_versions("1.0.0", "2.0.0") < 0
    assert manager._compare_versions("2.0.0", "1.0.0") > 0
    assert manager._compare_versions("1.0.0", "1.0.0") == 0


def test_extract_major_version():
    """Test extracting major version."""
    manager = SecurityOverlayManager()
    
    assert manager._extract_major_version("1.2.3") == 1
    assert manager._extract_major_version("2.0.0") == 2
    assert manager._extract_major_version("invalid") is None


def test_create_constraint_for_cve():
    """Test creating constraint from CVE."""
    manager = SecurityOverlayManager()
    
    cve = CVERecord(
        cve_id="CVE-2023-1234",
        package="requests",
        affected_versions=[">=2.0.0", "<2.31.0"],
        fixed_version="2.31.0",
        severity=Severity.CRITICAL,
    )
    
    manager._create_constraint_for_cve(cve)
    
    assert "requests" in manager.constraints
    constraint = manager.constraints["requests"]
    assert constraint.min_version == "2.31.0"
    assert "CVE-2023-1234" in constraint.cve_ids
