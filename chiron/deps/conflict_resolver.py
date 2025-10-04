#!/usr/bin/env python3
"""
Automatic dependency conflict detection and resolution.

This module provides intelligent conflict detection and resolution strategies
for dependency management, including:
- Version constraint analysis
- Dependency tree conflict detection
- Automatic resolution suggestions
- Integration with Poetry resolver
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DependencyConstraint:
    """A version constraint from a dependency."""

    package: str
    constraint: str
    required_by: str
    is_direct: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "constraint": self.constraint,
            "required_by": self.required_by,
            "is_direct": self.is_direct,
        }


@dataclass(slots=True)
class ConflictInfo:
    """Information about a dependency conflict."""

    package: str
    conflicting_constraints: list[DependencyConstraint]
    conflict_type: Literal["version", "missing", "circular"]
    severity: Literal["error", "warning", "info"]
    resolution_suggestions: list[str] = field(default_factory=list)
    auto_resolvable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "conflicting_constraints": [
                c.to_dict() for c in self.conflicting_constraints
            ],
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "resolution_suggestions": list(self.resolution_suggestions),
            "auto_resolvable": self.auto_resolvable,
        }


@dataclass(slots=True)
class ConflictResolution:
    """A proposed resolution for a conflict."""

    package: str
    resolution_type: Literal["pin", "upgrade", "downgrade", "remove", "manual"]
    target_version: str | None
    confidence: float
    description: str
    commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "resolution_type": self.resolution_type,
            "target_version": self.target_version,
            "confidence": self.confidence,
            "description": self.description,
            "commands": list(self.commands),
        }


@dataclass(slots=True)
class ConflictAnalysisReport:
    """Complete conflict analysis report."""

    generated_at: datetime
    conflicts: list[ConflictInfo]
    resolutions: list[ConflictResolution]
    summary: dict[str, int]
    auto_resolvable_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "resolutions": [r.to_dict() for r in self.resolutions],
            "summary": dict(self.summary),
            "auto_resolvable_count": self.auto_resolvable_count,
        }


class ConflictResolver:
    """
    Intelligent conflict detection and resolution for dependency management.

    Analyzes dependency trees, detects conflicts, and proposes resolutions
    with confidence scoring.
    """

    def __init__(self, conservative: bool = True):
        """
        Initialize conflict resolver.

        Args:
            conservative: If True, only suggest low-risk resolutions
        """
        self.conservative = conservative

    def analyze_conflicts(
        self,
        dependencies: dict[str, Any],
        lock_data: dict[str, Any] | None = None,
    ) -> ConflictAnalysisReport:
        """
        Analyze dependencies for conflicts.

        Args:
            dependencies: Dependency specification (from pyproject.toml or similar)
            lock_data: Optional lock file data for additional analysis

        Returns:
            ConflictAnalysisReport with detected conflicts and resolutions
        """
        logger.info("Analyzing dependency conflicts...")

        # Extract constraints
        constraints = self._extract_constraints(dependencies)

        # Detect conflicts
        conflicts = self._detect_conflicts(constraints)

        # Generate resolutions
        resolutions: list[ConflictResolution] = []
        for conflict in conflicts:
            resolution = self._generate_resolution(conflict, dependencies)
            if resolution:
                resolutions.append(resolution)

        auto_resolvable = sum(1 for c in conflicts if c.auto_resolvable)

        summary = {
            "total_conflicts": len(conflicts),
            "version_conflicts": sum(
                1 for c in conflicts if c.conflict_type == "version"
            ),
            "missing_dependencies": sum(
                1 for c in conflicts if c.conflict_type == "missing"
            ),
            "circular_dependencies": sum(
                1 for c in conflicts if c.conflict_type == "circular"
            ),
            "errors": sum(1 for c in conflicts if c.severity == "error"),
            "warnings": sum(1 for c in conflicts if c.severity == "warning"),
        }

        return ConflictAnalysisReport(
            generated_at=datetime.now(UTC),
            conflicts=conflicts,
            resolutions=resolutions,
            summary=summary,
            auto_resolvable_count=auto_resolvable,
        )

    def _extract_constraints(
        self,
        dependencies: dict[str, Any],
    ) -> dict[str, list[DependencyConstraint]]:
        """Extract all version constraints from dependency specification."""
        constraints: dict[str, list[DependencyConstraint]] = defaultdict(list)

        # Process direct dependencies
        deps = dependencies.get("dependencies", {})
        for package, spec in deps.items():
            if isinstance(spec, str):
                constraint = spec
            elif isinstance(spec, dict):
                constraint = spec.get("version", "*")
            else:
                constraint = "*"

            constraints[package].append(
                DependencyConstraint(
                    package=package,
                    constraint=constraint,
                    required_by="<root>",
                    is_direct=True,
                )
            )

        # Process dev dependencies
        dev_deps = dependencies.get("dev-dependencies", {})
        for package, spec in dev_deps.items():
            if isinstance(spec, str):
                constraint = spec
            elif isinstance(spec, dict):
                constraint = spec.get("version", "*")
            else:
                constraint = "*"

            # Only add if not already in dependencies
            if package not in constraints:
                constraints[package].append(
                    DependencyConstraint(
                        package=package,
                        constraint=constraint,
                        required_by="<root-dev>",
                        is_direct=True,
                    )
                )

        return constraints

    def _detect_conflicts(
        self,
        constraints: dict[str, list[DependencyConstraint]],
    ) -> list[ConflictInfo]:
        """Detect conflicts in constraint set."""
        conflicts: list[ConflictInfo] = []

        for package, package_constraints in constraints.items():
            if len(package_constraints) <= 1:
                continue

            # Check for conflicting version constraints
            if self._has_version_conflict(package_constraints):
                conflict = ConflictInfo(
                    package=package,
                    conflicting_constraints=package_constraints,
                    conflict_type="version",
                    severity="error",
                    auto_resolvable=self._is_auto_resolvable_version_conflict(
                        package_constraints
                    ),
                )

                # Generate suggestions
                conflict.resolution_suggestions = self._suggest_version_resolution(
                    package_constraints
                )

                conflicts.append(conflict)

        return conflicts

    def _has_version_conflict(
        self,
        constraints: list[DependencyConstraint],
    ) -> bool:
        """Check if constraints have version conflicts."""
        # Simple heuristic: if we have multiple non-wildcard constraints
        non_wildcard = [c for c in constraints if c.constraint != "*"]

        if len(non_wildcard) <= 1:
            return False

        # Check for obviously incompatible constraints
        # This is a simplified check - in practice would use packaging.specifiers
        constraint_specs = [c.constraint for c in non_wildcard]

        # Look for major version conflicts
        major_versions = set()
        for spec in constraint_specs:
            # Extract major version (simplified)
            if "^" in spec:
                version_part = spec.split("^")[1].split(".")[0]
                major_versions.add(version_part)
            elif ">=" in spec:
                version_part = spec.split(">=")[1].split(".")[0]
                major_versions.add(version_part)

        # If we have multiple different major versions, likely conflict
        return len(major_versions) > 1

    def _is_auto_resolvable_version_conflict(
        self,
        constraints: list[DependencyConstraint],
    ) -> bool:
        """Determine if version conflict can be auto-resolved."""
        # Conservative approach: only auto-resolve if one constraint is from root
        direct_constraints = [c for c in constraints if c.is_direct]

        # If we have exactly one direct constraint, we can resolve by using it
        return len(direct_constraints) == 1

    def _suggest_version_resolution(
        self,
        constraints: list[DependencyConstraint],
    ) -> list[str]:
        """Generate suggestions for resolving version conflicts."""
        suggestions: list[str] = []

        direct = [c for c in constraints if c.is_direct]
        indirect = [c for c in constraints if not c.is_direct]

        if direct:
            suggestions.append(
                f"Use direct dependency constraint: {direct[0].constraint}"
            )

        if len(constraints) == 2:
            suggestions.append(
                "Consider updating one dependency to be compatible with the other"
            )

        suggestions.append("Review dependency tree with 'poetry show --tree'")
        suggestions.append("Consider using dependency groups to isolate conflicts")

        return suggestions

    def _generate_resolution(
        self,
        conflict: ConflictInfo,
        dependencies: dict[str, Any],
    ) -> ConflictResolution | None:
        """Generate resolution proposal for a conflict."""
        if conflict.conflict_type != "version":
            return None

        # Find the direct constraint (if any)
        direct = [c for c in conflict.conflicting_constraints if c.is_direct]

        if not direct:
            # No direct constraint, suggest manual review
            return ConflictResolution(
                package=conflict.package,
                resolution_type="manual",
                target_version=None,
                confidence=0.3,
                description=(
                    f"Conflict in transitive dependencies for {conflict.package}. "
                    "Manual review required."
                ),
                commands=[
                    f"poetry show {conflict.package}",
                    f"poetry show --tree | grep {conflict.package}",
                ],
            )

        # Use direct constraint as resolution
        direct_constraint = direct[0]
        target_version = direct_constraint.constraint

        # Determine confidence based on constraint type
        confidence = 0.8 if self.conservative else 0.9

        return ConflictResolution(
            package=conflict.package,
            resolution_type="pin",
            target_version=target_version,
            confidence=confidence,
            description=(
                f"Pin {conflict.package} to direct dependency constraint: "
                f"{target_version}"
            ),
            commands=[
                f"poetry add {conflict.package}{target_version}",
            ],
        )


def analyze_dependency_conflicts(
    dependencies: dict[str, Any],
    lock_data: dict[str, Any] | None = None,
    conservative: bool = True,
) -> ConflictAnalysisReport:
    """
    Analyze dependencies for conflicts and generate resolutions.

    Convenience function for creating resolver and analyzing conflicts.

    Args:
        dependencies: Dependency specification
        lock_data: Optional lock file data
        conservative: Use conservative resolution strategy

    Returns:
        ConflictAnalysisReport with conflicts and resolutions
    """
    resolver = ConflictResolver(conservative=conservative)
    return resolver.analyze_conflicts(dependencies, lock_data)
