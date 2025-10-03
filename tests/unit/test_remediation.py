"""Tests for the wheelhouse remediation helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from prometheus.remediation import WheelhouseRemediator, parse_missing_wheel_failures


def test_parse_missing_wheel_failures_detects_packages() -> None:
    log = """
    ERROR: No matching distribution found for numpy==2.3.2
    ERROR: Some unrelated message
    ERROR: No matching distribution found for pandas==2.2.0
    """.strip()

    failures = parse_missing_wheel_failures(log)

    assert [failure.package for failure in failures] == ["numpy", "pandas"]
    assert [failure.requested_version for failure in failures] == ["2.3.2", "2.2.0"]


def test_build_summary_infers_fallback_version(tmp_path: Path) -> None:
    releases = {
        "2.3.2": [
            {
                "packagetype": "bdist_wheel",
                "filename": "numpy-2.3.2-cp310-cp310-manylinux2014_x86_64.whl",
                "requires_python": ">=3.10",
            }
        ],
        "2.3.1": [
            {
                "packagetype": "bdist_wheel",
                "filename": "numpy-2.3.1-cp310-cp310-manylinux2014_x86_64.whl",
                "requires_python": ">=3.10",
            }
        ],
        "2.3.0": [
            {
                "packagetype": "bdist_wheel",
                "filename": "numpy-2.3.0-cp39-cp39-manylinux2014_x86_64.whl",
                "requires_python": ">=3.9",
            }
        ],
    }
    release_payload = cast(Mapping[str, object], {"releases": releases})

    def fake_fetcher(package: str) -> Mapping[str, object] | None:
        assert package == "numpy"
        return release_payload

    remediator = WheelhouseRemediator(
        python_version="3.10",
        platform="manylinux2014_x86_64",
        fetch_package=fake_fetcher,
    )

    log = "ERROR: No matching distribution found for numpy==2.3.2"
    summary = remediator.build_summary(log)
    assert summary is not None
    assert isinstance(summary, dict)

    failures = summary.get("failures")
    assert isinstance(failures, list)
    failure_entry = failures[0]
    assert failure_entry["fallback_version"] == "2.3.1"
    assert any("ALLOW_SDIST_FOR" in rec for rec in failure_entry["recommendations"])

    log_path = tmp_path / "log.txt"
    output_path = tmp_path / "remediation.json"
    log_path.write_text("INFO: all good\n")

    summary_if_any = remediator.write_summary(log_path, output_path)
    assert summary_if_any is None
    assert not output_path.exists()

    log_path.write_text(log)
    summary_created = remediator.write_summary(log_path, output_path)
    assert summary_created is not None
    assert output_path.exists()
    content = output_path.read_text()
    assert "numpy" in content and "2.3.2" in content


def test_build_summary_handles_multiple_failures(tmp_path: Path) -> None:
    releases = {
        "numpy": cast(
            Mapping[str, object],
            {
                "releases": {
                    "2.3.2": [
                        {
                            "packagetype": "bdist_wheel",
                            "filename": "numpy-2.3.2-cp310-cp310-manylinux2014_x86_64.whl",
                            "requires_python": ">=3.10",
                        }
                    ],
                    "2.3.1": [
                        {
                            "packagetype": "bdist_wheel",
                            "filename": "numpy-2.3.1-cp310-cp310-manylinux2014_x86_64.whl",
                            "requires_python": ">=3.10",
                        }
                    ],
                }
            },
        ),
        "pandas": cast(
            Mapping[str, object],
            {
                "releases": {
                    "2.2.0": [
                        {
                            "packagetype": "bdist_wheel",
                            "filename": "pandas-2.2.0-cp311-cp311-manylinux2014_x86_64.whl",
                            "requires_python": ">=3.11",
                        }
                    ],
                    "2.1.4": [
                        {
                            "packagetype": "bdist_wheel",
                            "filename": "pandas-2.1.4-cp310-cp310-manylinux2014_x86_64.whl",
                            "requires_python": ">=3.10",
                        }
                    ],
                }
            },
        ),
    }

    def fake_fetcher(package: str) -> Mapping[str, object] | None:
        return releases.get(package)

    remediator = WheelhouseRemediator(
        python_version="3.10",
        platform="manylinux2014_x86_64",
        fetch_package=fake_fetcher,
    )

    log = (
        "ERROR: No matching distribution found for numpy==2.3.2\n"
        "ERROR: No matching distribution found for pandas==2.2.0"
    )

    summary = remediator.build_summary(log)
    assert summary is not None
    failures = summary.get("failures")
    assert isinstance(failures, list)
    assert len(failures) == 2

    failure_map = {entry["package"]: entry for entry in failures}
    assert failure_map["numpy"]["fallback_version"] == "2.3.1"
    assert failure_map["pandas"]["fallback_version"] == "2.1.4"

    log_path = tmp_path / "multi.log"
    output_path = tmp_path / "multi-summary.json"
    log_path.write_text(log)

    result = remediator.write_summary(log_path, output_path)
    assert result is not None
    saved = json.loads(output_path.read_text())
    saved_failures = {entry["package"] for entry in saved["failures"]}
    assert saved_failures == {"numpy", "pandas"}
