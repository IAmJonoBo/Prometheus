"""Tests for binary reproducibility checks."""

import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from chiron.deps.reproducibility import (
    ReproducibilityChecker,
    ReproducibilityReport,
    WheelDigest,
)


@pytest.fixture
def sample_wheel(tmp_path):
    """Create a sample wheel file."""
    wheel_path = tmp_path / "sample-1.0.0-py3-none-any.whl"

    with zipfile.ZipFile(wheel_path, "w") as zf:
        # Add METADATA
        metadata = """Metadata-Version: 2.1
Name: sample
Version: 1.0.0
"""
        zf.writestr("sample-1.0.0.dist-info/METADATA", metadata)

        # Add WHEEL
        wheel_info = """Wheel-Version: 1.0
Generator: test
Root-Is-Purelib: true
Tag: py3-none-any
"""
        zf.writestr("sample-1.0.0.dist-info/WHEEL", wheel_info)

        # Add RECORD
        zf.writestr("sample-1.0.0.dist-info/RECORD", "")

        # Add module
        zf.writestr("sample/__init__.py", "# Sample module\n")

    return wheel_path


@pytest.fixture
def wheelhouse_dir(tmp_path, sample_wheel):
    """Create a wheelhouse directory with sample wheels."""
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    import shutil

    shutil.copy(sample_wheel, wheelhouse / sample_wheel.name)

    return wheelhouse


def test_reproducibility_checker_init():
    """Test ReproducibilityChecker initialization."""
    checker = ReproducibilityChecker(normalize=True)

    assert checker.normalize is True


def test_compute_wheel_digest(sample_wheel):
    """Test computing wheel digest."""
    checker = ReproducibilityChecker()

    digest = checker.compute_wheel_digest(sample_wheel)

    assert isinstance(digest, WheelDigest)
    assert digest.filename == sample_wheel.name
    assert len(digest.sha256) == 64  # SHA256 hex length
    assert digest.size > 0
    assert "name" in digest.metadata
    assert digest.metadata["name"] == "sample"


def test_compare_identical_wheels(sample_wheel):
    """Test comparing identical wheels."""
    checker = ReproducibilityChecker()

    report = checker.compare_wheels(sample_wheel, sample_wheel)

    assert isinstance(report, ReproducibilityReport)
    assert report.is_reproducible is True
    assert report.size_match is True
    assert report.original_digest == report.rebuilt_digest
    assert len(report.differences) == 0


def test_compare_different_wheels(tmp_path, sample_wheel):
    """Test comparing different wheels."""
    # Create a modified version
    modified_wheel = tmp_path / "modified.whl"

    with zipfile.ZipFile(sample_wheel, "r") as zf_in:
        with zipfile.ZipFile(modified_wheel, "w") as zf_out:
            for item in zf_in.infolist():
                data = zf_in.read(item.filename)
                if item.filename == "sample/__init__.py":
                    data = b"# Modified module\n"
                zf_out.writestr(item, data)

    checker = ReproducibilityChecker()
    report = checker.compare_wheels(sample_wheel, modified_wheel)

    assert report.is_reproducible is False
    assert len(report.differences) > 0


def test_save_digests(wheelhouse_dir):
    """Test saving wheel digests."""
    checker = ReproducibilityChecker()

    output_file = wheelhouse_dir / "digests.json"
    checker.save_digests(wheelhouse_dir, output_file)

    assert output_file.exists()

    import json

    data = json.loads(output_file.read_text())

    assert len(data) > 0
    for wheel_name, digest_info in data.items():
        assert "sha256" in digest_info
        assert "size" in digest_info


def test_verify_against_digests(wheelhouse_dir):
    """Test verifying wheels against saved digests."""
    checker = ReproducibilityChecker()

    # Save digests
    digests_file = wheelhouse_dir / "digests.json"
    checker.save_digests(wheelhouse_dir, digests_file)

    # Verify
    reports = checker.verify_against_digests(wheelhouse_dir, digests_file)

    assert len(reports) > 0
    for report in reports.values():
        assert report.is_reproducible is True


def test_verify_wheelhouse(wheelhouse_dir):
    """Test verifying entire wheelhouse."""
    checker = ReproducibilityChecker()

    reports = checker.verify_wheelhouse(wheelhouse_dir)

    assert len(reports) > 0
    for wheel_name, report in reports.items():
        assert report.wheel_name == wheel_name


def test_wheel_digest_dataclass():
    """Test WheelDigest dataclass."""
    digest = WheelDigest(
        filename="test.whl",
        sha256="abc123",
        size=1024,
        metadata={"name": "test", "version": "1.0.0"},
    )

    assert digest.filename == "test.whl"
    assert digest.sha256 == "abc123"
    assert digest.size == 1024
    assert digest.metadata["name"] == "test"


def test_reproducibility_report_dataclass():
    """Test ReproducibilityReport dataclass."""
    report = ReproducibilityReport(
        wheel_name="test.whl",
        is_reproducible=True,
        original_digest="abc123",
        rebuilt_digest="abc123",
        size_match=True,
    )

    assert report.wheel_name == "test.whl"
    assert report.is_reproducible is True
    assert report.size_match is True


def test_normalized_patterns():
    """Test normalized patterns list."""
    checker = ReproducibilityChecker()

    assert "*.pyc" in checker.NORMALIZED_PATTERNS
    assert "RECORD" in checker.NORMALIZED_PATTERNS
