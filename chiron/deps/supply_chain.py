#!/usr/bin/env python3
"""
Supply chain security tools: SBOM generation and vulnerability scanning.

Provides CycloneDX SBOM generation and OSV-based vulnerability scanning
with CI gate integration.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VulnerabilitySummary:
    """Summary of vulnerability scan results."""

    total_vulnerabilities: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    packages_affected: list[str] = field(default_factory=list)
    scan_timestamp: str = ""

    def has_blocking_vulnerabilities(self, max_severity: str = "high") -> bool:
        """
        Check if there are blocking vulnerabilities.

        Args:
            max_severity: Maximum allowed severity ('critical', 'high', 'medium', 'low')

        Returns:
            True if blocking vulnerabilities found
        """
        severity_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        threshold = severity_order.get(max_severity, 2)

        if threshold >= 3 and self.critical > 0:
            return True
        if threshold >= 2 and self.high > 0:
            return True
        if threshold >= 1 and self.medium > 0:
            return True

        return False


class SBOMGenerator:
    """Generate CycloneDX SBOM for the project."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def generate(
        self,
        output_path: Path,
        format: str = "json",
    ) -> bool:
        """
        Generate SBOM using cyclonedx-py.

        Args:
            output_path: Path for output SBOM file
            format: Output format ('json' or 'xml')

        Returns:
            True if successful, False otherwise
        """
        cyclonedx = shutil.which("cyclonedx-py")
        if not cyclonedx:
            logger.error(
                "cyclonedx-py not found. " "Install with: pip install cyclonedx-bom"
            )
            return False

        cmd = [
            cyclonedx,
            "--format",
            format,
            "-o",
            str(output_path),
            str(self.project_root),
        ]

        try:
            logger.info(f"Generating SBOM: {output_path}")
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"SBOM generation failed: {result.stderr}")
                return False

            if not output_path.exists():
                logger.error(f"SBOM file not created: {output_path}")
                return False

            logger.info(f"Generated SBOM: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error generating SBOM: {e}")
            return False


class OSVScanner:
    """Scan for vulnerabilities using OSV."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def scan_lockfile(
        self,
        lockfile_path: Path,
        output_path: Path | None = None,
    ) -> VulnerabilitySummary | None:
        """
        Scan a lockfile for vulnerabilities.

        Args:
            lockfile_path: Path to lockfile (requirements.txt, poetry.lock, etc.)
            output_path: Optional path to save JSON report

        Returns:
            VulnerabilitySummary or None if scan failed
        """
        osv_scanner = shutil.which("osv-scanner")
        if not osv_scanner:
            logger.error(
                "osv-scanner not found. "
                "Install from: https://github.com/google/osv-scanner"
            )
            return None

        cmd = [
            osv_scanner,
            "--lockfile",
            str(lockfile_path),
            "--format",
            "json",
        ]

        try:
            logger.info(f"Scanning {lockfile_path} for vulnerabilities...")
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            # OSV scanner returns non-zero if vulnerabilities found
            if result.stdout:
                scan_data = json.loads(result.stdout)
            else:
                scan_data = {"results": []}

            # Save report if requested
            if output_path:
                output_path.write_text(json.dumps(scan_data, indent=2))
                logger.info(f"Saved vulnerability report: {output_path}")

            # Parse results
            summary = self._parse_results(scan_data)

            if summary.total_vulnerabilities > 0:
                logger.warning(
                    f"Found {summary.total_vulnerabilities} vulnerabilities: "
                    f"critical={summary.critical}, high={summary.high}, "
                    f"medium={summary.medium}, low={summary.low}"
                )
            else:
                logger.info("No vulnerabilities found")

            return summary

        except Exception as e:
            logger.error(f"Error scanning for vulnerabilities: {e}")
            return None

    def _parse_results(self, scan_data: dict[str, Any]) -> VulnerabilitySummary:
        """Parse OSV scan results into summary."""
        summary = VulnerabilitySummary(
            scan_timestamp=datetime.now(UTC).isoformat(),
        )

        results = scan_data.get("results", [])
        packages_affected = set()

        for result in results:
            packages = result.get("packages", [])
            for pkg in packages:
                pkg_name = pkg.get("package", {}).get("name", "unknown")
                packages_affected.add(pkg_name)

                vulnerabilities = pkg.get("vulnerabilities", [])
                for vuln in vulnerabilities:
                    summary.total_vulnerabilities += 1

                    # Try to determine severity
                    severity = vuln.get("severity", "")
                    if not severity:
                        # Try to infer from CVSS score or other fields
                        database_specific = vuln.get("database_specific", {})
                        severity = database_specific.get("severity", "unknown")

                    severity_lower = str(severity).lower()
                    if "critical" in severity_lower:
                        summary.critical += 1
                    elif "high" in severity_lower:
                        summary.high += 1
                    elif "medium" in severity_lower or "moderate" in severity_lower:
                        summary.medium += 1
                    elif "low" in severity_lower:
                        summary.low += 1

        summary.packages_affected = sorted(packages_affected)

        return summary


def generate_sbom_and_scan(
    project_root: Path,
    sbom_output: Path,
    osv_output: Path,
    lockfile_path: Path,
    gate_max_severity: str = "high",
) -> tuple[bool, VulnerabilitySummary | None]:
    """
    Generate SBOM and perform vulnerability scan as CI gate.

    Args:
        project_root: Root directory of the project
        sbom_output: Path for SBOM output
        osv_output: Path for OSV scan output
        lockfile_path: Path to lockfile to scan
        gate_max_severity: Maximum severity to allow ('critical', 'high', 'medium', 'low')

    Returns:
        Tuple of (success, vulnerability_summary)
        success is False if gate fails
    """
    # Generate SBOM
    sbom_gen = SBOMGenerator(project_root)
    if not sbom_gen.generate(sbom_output):
        logger.error("SBOM generation failed")
        return False, None

    # Run OSV scan
    scanner = OSVScanner(project_root)
    summary = scanner.scan_lockfile(lockfile_path, osv_output)

    if summary is None:
        logger.error("Vulnerability scan failed")
        return False, None

    # Check gate
    if summary.has_blocking_vulnerabilities(gate_max_severity):
        logger.error(
            f"Security gate failed: Found blocking vulnerabilities "
            f"(max severity: {gate_max_severity})"
        )
        return False, summary

    logger.info("Security checks passed")
    return True, summary
