"""Unit tests for dependency drift analysis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import dependency_drift


@pytest.fixture()
def sbom_tmp(tmp_path: Path) -> Path:
    sbom = {
        "components": [
            {
                "name": "requests",
                "version": "2.30.0",
            },
            {
                "name": "numpy",
                "version": "1.26.4",
            },
        ]
    }
    path = tmp_path / "sbom.json"
    path.write_text(json.dumps(sbom), encoding="utf-8")
    return path


@pytest.fixture()
def metadata_tmp(tmp_path: Path) -> Path:
    metadata = {
        "packages": {
            "requests": {"latest": "2.32.3"},
            "numpy": {"latest": "1.26.4"},
        }
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    return path


def test_evaluate_drift_identifies_patch_and_uptodate(
    sbom_tmp: Path, metadata_tmp: Path
) -> None:
    components = dependency_drift.load_sbom(sbom_tmp)
    metadata = dependency_drift.load_metadata(metadata_tmp)
    policy = dependency_drift.parse_policy({})

    report = dependency_drift.evaluate_drift(components, metadata, policy)

    assert report.severity == dependency_drift.RISK_MINOR  # due to requests minor jump
    requests_pkg = next(pkg for pkg in report.packages if pkg.name == "requests")
    numpy_pkg = next(pkg for pkg in report.packages if pkg.name == "numpy")
    assert requests_pkg.severity == dependency_drift.RISK_MINOR
    assert "minor upgrade available" in requests_pkg.notes[0]
    assert numpy_pkg.severity == dependency_drift.RISK_SAFE


def test_evaluate_drift_handles_missing_metadata(sbom_tmp: Path) -> None:
    components = dependency_drift.load_sbom(sbom_tmp)
    policy = dependency_drift.parse_policy({})

    report = dependency_drift.evaluate_drift(components, {}, policy)

    assert report.severity == dependency_drift.RISK_UNKNOWN
    assert "Metadata snapshot" in report.notes[0]


def test_classify_major_upgrade_respects_override() -> None:
    policy = dependency_drift.parse_policy(
        {
            "package_overrides": [
                {"name": "requests", "stay_on_major": 2},
            ]
        }
    )
    severity, notes = dependency_drift._classify_drift(
        "requests", "1.0.0", "2.0.0", policy
    )
    assert severity == dependency_drift.RISK_MAJOR
    assert any("major upgrades require override" in note for note in notes)
