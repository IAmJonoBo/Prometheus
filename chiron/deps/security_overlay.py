#!/usr/bin/env python3
"""Security constraints overlay for CVE backport management.

This module helps manage security patches by tracking CVEs and generating
constraint overlays that pin safe versions without jumping major versions.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    """CVE severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str) -> Severity:
        """Convert string to Severity enum."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.UNKNOWN


@dataclass
class CVERecord:
    """CVE vulnerability record."""

    cve_id: str
    package: str
    affected_versions: list[str]
    fixed_version: str
    severity: Severity
    description: str = ""
    published_date: str = ""
    references: list[str] = field(default_factory=list)


@dataclass
class SecurityConstraint:
    """Security constraint for a package."""

    package: str
    min_version: str
    max_version: str | None = None
    reason: str = ""
    cve_ids: list[str] = field(default_factory=list)


class SecurityOverlayManager:
    """Manage security constraints overlay."""

    def __init__(self, overlay_file: Path | None = None):
        """Initialize security overlay manager.

        Args:
            overlay_file: Path to security overlay file
        """
        self.overlay_file = overlay_file or Path("security-constraints.json")
        self.constraints: dict[str, SecurityConstraint] = {}
        self.cve_database: dict[str, CVERecord] = {}

        if self.overlay_file.exists():
            self._load_overlay()

    def _load_overlay(self) -> None:
        """Load security overlay from file."""
        data = json.loads(self.overlay_file.read_text())

        for pkg_name, constraint_data in data.get("constraints", {}).items():
            self.constraints[pkg_name] = SecurityConstraint(
                package=pkg_name,
                min_version=constraint_data["min_version"],
                max_version=constraint_data.get("max_version"),
                reason=constraint_data.get("reason", ""),
                cve_ids=constraint_data.get("cve_ids", []),
            )

        for cve_id, cve_data in data.get("cve_database", {}).items():
            self.cve_database[cve_id] = CVERecord(
                cve_id=cve_id,
                package=cve_data["package"],
                affected_versions=cve_data["affected_versions"],
                fixed_version=cve_data["fixed_version"],
                severity=Severity.from_string(cve_data.get("severity", "unknown")),
                description=cve_data.get("description", ""),
                published_date=cve_data.get("published_date", ""),
                references=cve_data.get("references", []),
            )

    def save_overlay(self) -> None:
        """Save security overlay to file."""
        data = {
            "version": "1.0",
            "updated": datetime.now().isoformat(),
            "constraints": {},
            "cve_database": {},
        }

        for pkg_name, constraint in self.constraints.items():
            data["constraints"][pkg_name] = {
                "min_version": constraint.min_version,
                "max_version": constraint.max_version,
                "reason": constraint.reason,
                "cve_ids": constraint.cve_ids,
            }

        for cve_id, cve in self.cve_database.items():
            data["cve_database"][cve_id] = {
                "package": cve.package,
                "affected_versions": cve.affected_versions,
                "fixed_version": cve.fixed_version,
                "severity": cve.severity.value,
                "description": cve.description,
                "published_date": cve.published_date,
                "references": cve.references,
            }

        self.overlay_file.write_text(json.dumps(data, indent=2))
        print(f"Saved security overlay to {self.overlay_file}")

    def import_osv_scan(self, osv_file: Path) -> int:
        """Import vulnerabilities from OSV scan results.

        Args:
            osv_file: Path to OSV scan JSON output

        Returns:
            Number of CVEs imported
        """
        osv_data = json.loads(osv_file.read_text())
        imported_count = 0

        for result in osv_data.get("results", []):
            for package_result in result.get("packages", []):
                package_name = package_result.get("package", {}).get("name", "unknown")

                for vuln in package_result.get("vulnerabilities", []):
                    cve_id = vuln.get("id", f"UNKNOWN-{imported_count}")

                    # Parse affected versions
                    affected_versions = []
                    for affected in vuln.get("affected", []):
                        for version_range in affected.get("ranges", []):
                            events = version_range.get("events", [])
                            for event in events:
                                if "introduced" in event:
                                    affected_versions.append(f">={event['introduced']}")
                                elif "fixed" in event:
                                    affected_versions.append(f"<{event['fixed']}")

                    # Get fixed version (from first fixed event)
                    fixed_version = ""
                    for affected in vuln.get("affected", []):
                        for version_range in affected.get("ranges", []):
                            for event in version_range.get("events", []):
                                if "fixed" in event:
                                    fixed_version = event["fixed"]
                                    break
                            if fixed_version:
                                break
                        if fixed_version:
                            break

                    # Determine severity
                    severity = Severity.UNKNOWN
                    for severity_entry in vuln.get("database_specific", {}).get(
                        "severity", []
                    ):
                        if severity_entry.get("type") == "CVSS_V3":
                            score = float(severity_entry.get("score", "0.0"))
                            if score >= 9.0:
                                severity = Severity.CRITICAL
                            elif score >= 7.0:
                                severity = Severity.HIGH
                            elif score >= 4.0:
                                severity = Severity.MEDIUM
                            else:
                                severity = Severity.LOW

                    cve_record = CVERecord(
                        cve_id=cve_id,
                        package=package_name,
                        affected_versions=affected_versions,
                        fixed_version=fixed_version,
                        severity=severity,
                        description=vuln.get("summary", ""),
                        published_date=vuln.get("published", ""),
                        references=[
                            ref.get("url", "") for ref in vuln.get("references", [])
                        ],
                    )

                    self.cve_database[cve_id] = cve_record
                    imported_count += 1

                    # Create or update constraint if severity is high enough
                    if severity in [Severity.CRITICAL, Severity.HIGH]:
                        self._create_constraint_for_cve(cve_record)

        self.save_overlay()
        print(f"Imported {imported_count} CVEs from OSV scan")
        return imported_count

    def _create_constraint_for_cve(self, cve: CVERecord) -> None:
        """Create security constraint for a CVE.

        Args:
            cve: CVE record
        """
        if not cve.fixed_version:
            print(f"  Warning: No fixed version for {cve.cve_id}, skipping constraint")
            return

        # Get or create constraint
        if cve.package in self.constraints:
            constraint = self.constraints[cve.package]
            # Update to most recent fixed version
            if self._compare_versions(cve.fixed_version, constraint.min_version) > 0:
                constraint.min_version = cve.fixed_version
            if cve.cve_id not in constraint.cve_ids:
                constraint.cve_ids.append(cve.cve_id)
        else:
            # Extract major version to set ceiling
            major_version = self._extract_major_version(cve.fixed_version)
            max_version = (
                f"<{major_version + 1}.0" if major_version is not None else None
            )

            constraint = SecurityConstraint(
                package=cve.package,
                min_version=cve.fixed_version,
                max_version=max_version,
                reason=f"Security fix for {cve.severity.value} severity issues",
                cve_ids=[cve.cve_id],
            )
            self.constraints[cve.package] = constraint

        print(f"  ✓ Created constraint: {cve.package}>={cve.fixed_version}")

    def _extract_major_version(self, version: str) -> int | None:
        """Extract major version number from version string.

        Args:
            version: Version string (e.g., "1.2.3")

        Returns:
            Major version number or None
        """
        match = re.match(r"^(\d+)\.", version)
        if match:
            return int(match.group(1))
        return None

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings.

        Args:
            v1: First version
            v2: Second version

        Returns:
            -1 if v1 < v2, 0 if equal, 1 if v1 > v2
        """
        # Simple version comparison (can be improved with packaging.version)
        parts1 = [int(x) for x in re.findall(r"\d+", v1)]
        parts2 = [int(x) for x in re.findall(r"\d+", v2)]

        for p1, p2 in zip(parts1, parts2):
            if p1 < p2:
                return -1
            elif p1 > p2:
                return 1

        # If all parts match, longer version is greater
        if len(parts1) < len(parts2):
            return -1
        elif len(parts1) > len(parts2):
            return 1

        return 0

    def generate_constraints_file(self, output_file: Path) -> None:
        """Generate pip constraints file from security overlay.

        Args:
            output_file: Path to output constraints file
        """
        lines = [
            "# Security constraints overlay",
            f"# Generated: {datetime.now().isoformat()}",
            "# DO NOT EDIT MANUALLY - Generated by security overlay manager",
            "",
        ]

        for pkg_name, constraint in sorted(self.constraints.items()):
            # Build constraint spec
            spec_parts = [f"{pkg_name}>={constraint.min_version}"]

            if constraint.max_version:
                spec_parts.append(constraint.max_version)

            constraint_spec = ",".join(spec_parts)

            # Add comment with CVEs
            if constraint.cve_ids:
                cve_list = ", ".join(constraint.cve_ids)
                lines.append(f"# {pkg_name}: {constraint.reason} ({cve_list})")

            lines.append(constraint_spec)
            lines.append("")

        output_file.write_text("\n".join(lines))
        print(f"Generated constraints file: {output_file}")
        print(f"  {len(self.constraints)} security constraints")

    def check_package_version(
        self,
        package: str,
        version: str,
    ) -> tuple[bool, list[str]]:
        """Check if a package version satisfies security constraints.

        Args:
            package: Package name
            version: Version to check

        Returns:
            Tuple of (is_safe, list of violations)
        """
        if package not in self.constraints:
            return True, []

        constraint = self.constraints[package]
        violations = []

        # Check minimum version
        if self._compare_versions(version, constraint.min_version) < 0:
            violations.append(
                f"Version {version} is below minimum {constraint.min_version}"
            )
            for cve_id in constraint.cve_ids:
                if cve_id in self.cve_database:
                    cve = self.cve_database[cve_id]
                    violations.append(f"  Affected by {cve_id} ({cve.severity.value})")

        # Check maximum version
        if constraint.max_version:
            # Parse max version constraint (e.g., "<2.0")
            match = re.match(r"<(\d+\.\d+)", constraint.max_version)
            if match:
                max_ver = match.group(1)
                if self._compare_versions(version, max_ver) >= 0:
                    violations.append(
                        f"Version {version} exceeds maximum {constraint.max_version}"
                    )

        return len(violations) == 0, violations

    def get_recommendations(self, package: str) -> list[str]:
        """Get version recommendations for a package.

        Args:
            package: Package name

        Returns:
            List of recommended versions
        """
        if package not in self.constraints:
            return []

        constraint = self.constraints[package]
        recommendations = [
            f"Minimum safe version: {constraint.min_version}",
        ]

        if constraint.max_version:
            recommendations.append(
                f"Stay below major version: {constraint.max_version}"
            )

        if constraint.cve_ids:
            recommendations.append(f"Addresses CVEs: {', '.join(constraint.cve_ids)}")

        return recommendations


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Security constraints overlay manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Import from OSV
    import_parser = subparsers.add_parser(
        "import-osv", help="Import CVEs from OSV scan"
    )
    import_parser.add_argument(
        "osv_file", type=Path, help="Path to OSV scan JSON output"
    )
    import_parser.add_argument(
        "--overlay",
        type=Path,
        default=Path("security-constraints.json"),
        help="Security overlay file",
    )

    # Generate constraints
    generate_parser = subparsers.add_parser(
        "generate", help="Generate pip constraints file"
    )
    generate_parser.add_argument(
        "--overlay",
        type=Path,
        default=Path("security-constraints.json"),
        help="Security overlay file",
    )
    generate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("security-constraints.txt"),
        help="Output constraints file",
    )

    # Check package
    check_parser = subparsers.add_parser(
        "check", help="Check package version against security constraints"
    )
    check_parser.add_argument("package", help="Package name")
    check_parser.add_argument("version", help="Version to check")
    check_parser.add_argument(
        "--overlay",
        type=Path,
        default=Path("security-constraints.json"),
        help="Security overlay file",
    )

    args = parser.parse_args()

    manager = SecurityOverlayManager(overlay_file=getattr(args, "overlay", None))

    if args.command == "import-osv":
        count = manager.import_osv_scan(args.osv_file)
        print(f"\n✓ Imported {count} CVEs")

    elif args.command == "generate":
        manager.generate_constraints_file(args.output)

    elif args.command == "check":
        is_safe, violations = manager.check_package_version(args.package, args.version)

        print(f"\nPackage: {args.package}=={args.version}")
        if is_safe:
            print("✓ Safe - meets security constraints")
        else:
            print("✗ Violations found:")
            for violation in violations:
                print(f"  - {violation}")

            print("\nRecommendations:")
            for rec in manager.get_recommendations(args.package):
                print(f"  • {rec}")

        sys.exit(0 if is_safe else 1)
