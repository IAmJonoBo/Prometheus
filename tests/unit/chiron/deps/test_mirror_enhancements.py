"""Tests for mirror manager enhancements."""

from __future__ import annotations

from pathlib import Path

import pytest

from chiron.deps.mirror_manager import (
    MirrorPackageInfo,
    check_package_availability,
    get_mirror_recommendations,
)


def test_package_info_creation():
    """Test MirrorPackageInfo can be created."""
    info = MirrorPackageInfo(
        name="test-pkg",
        version="1.0.0",
        available=True,
    )

    assert info.name == "test-pkg"
    assert info.version == "1.0.0"
    assert info.available is True


def test_package_info_serialization():
    """Test MirrorPackageInfo serialization."""
    info = MirrorPackageInfo(
        name="test-pkg",
        version="1.0.0",
        available=True,
    )

    info_dict = info.to_dict()
    assert info_dict["name"] == "test-pkg"
    assert info_dict["version"] == "1.0.0"
    assert info_dict["available"] is True


def test_check_availability_nonexistent_mirror(tmp_path):
    """Test checking availability in non-existent mirror."""
    mirror_root = tmp_path / "nonexistent"

    info = check_package_availability(mirror_root, "test-pkg")

    assert info.name == "test-pkg"
    assert info.available is False


def test_get_mirror_recommendations_empty(tmp_path):
    """Test getting recommendations with empty mirror."""
    mirror_root = tmp_path / "mirror"
    mirror_root.mkdir()

    packages_needed = [
        ("requests", "2.31.0"),
        ("urllib3", "1.26.18"),
    ]

    recommendations = get_mirror_recommendations(mirror_root, packages_needed)

    assert recommendations["summary"]["total"] == 2
    assert recommendations["summary"]["to_add"] == 2
    assert recommendations["summary"]["available"] == 0


def test_mirror_recommendations_serialization(tmp_path):
    """Test mirror recommendations can be serialized."""
    mirror_root = tmp_path / "mirror"
    mirror_root.mkdir()

    packages = [("test-pkg", "1.0.0")]

    recommendations = get_mirror_recommendations(mirror_root, packages)

    assert "summary" in recommendations
    assert "packages_to_add" in recommendations
    assert isinstance(recommendations, dict)
