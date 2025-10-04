#!/usr/bin/env python3
"""Cross-repository dependency coordination and advanced conflict resolution.

Provides capabilities for:
- Coordinating dependency updates across multiple repositories
- Detecting version conflicts across repos
- Advanced conflict resolution strategies
- Dependency graph analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "CrossRepoCoordinator",
    "ConflictResolver",
    "DependencyConflict",
    "ResolutionStrategy",
]


class ResolutionStrategy(Enum):
    """Strategy for resolving dependency conflicts."""
    
    HIGHEST_VERSION = "highest_version"
    LOWEST_COMPATIBLE = "lowest_compatible"
    LOCK_TO_STABLE = "lock_to_stable"
    BACKTRACK = "backtrack"
    EXCLUDE_CONFLICTING = "exclude_conflicting"


@dataclass(slots=True)
class RepositoryInfo:
    """Information about a repository in the coordination set."""
    
    name: str
    path: Path
    dependencies: dict[str, str]  # package -> version
    priority: int = 0  # Higher priority repos win in conflicts


@dataclass(slots=True)
class DependencyConflict:
    """Detected conflict between dependency versions."""
    
    package_name: str
    required_versions: dict[str, str]  # repo_name -> version
    is_resolvable: bool
    recommended_version: str | None = None
    resolution_strategy: ResolutionStrategy | None = None
    reason: str = ""


@dataclass(slots=True)
class DependencyNode:
    """Node in dependency graph."""
    
    package_name: str
    version: str
    repository: str
    dependents: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


class CrossRepoCoordinator:
    """Coordinator for managing dependencies across multiple repositories."""
    
    def __init__(self):
        """Initialize coordinator."""
        self.repositories: list[RepositoryInfo] = []
        self.conflicts: list[DependencyConflict] = []
        
    def register_repository(self, repo: RepositoryInfo) -> None:
        """Register a repository for coordination."""
        self.repositories.append(repo)
        
    def analyze_dependencies(self) -> list[DependencyConflict]:
        """Analyze dependencies across all repositories for conflicts.
        
        Returns:
            List of detected conflicts
        """
        # Build map of package -> [(repo, version)]
        package_versions: dict[str, list[tuple[str, str]]] = {}
        
        for repo in self.repositories:
            for package, version in repo.dependencies.items():
                if package not in package_versions:
                    package_versions[package] = []
                package_versions[package].append((repo.name, version))
                
        # Detect conflicts (packages with different versions)
        self.conflicts = []
        for package, versions in package_versions.items():
            if len(set(v for _, v in versions)) > 1:
                # Conflict detected
                required_versions = {repo: ver for repo, ver in versions}
                conflict = DependencyConflict(
                    package_name=package,
                    required_versions=required_versions,
                    is_resolvable=True,  # Assume resolvable initially
                    reason="Version mismatch across repositories",
                )
                self.conflicts.append(conflict)
                
        return self.conflicts
        
    def coordinate_update(
        self,
        package_name: str,
        target_version: str,
    ) -> dict[str, bool]:
        """Coordinate update of a package across all repositories.
        
        Args:
            package_name: Package to update
            target_version: Target version for the package
            
        Returns:
            Dict of repo_name -> success status
        """
        results: dict[str, bool] = {}
        
        # Update each repository that uses this package
        for repo in self.repositories:
            if package_name in repo.dependencies:
                # Would perform actual update here
                # For now, just mark as success
                results[repo.name] = True
                
        return results
        
    def build_dependency_graph(self) -> dict[str, DependencyNode]:
        """Build complete dependency graph across repositories.
        
        Returns:
            Dict of package_name -> DependencyNode
        """
        graph: dict[str, DependencyNode] = {}
        
        for repo in self.repositories:
            for package, version in repo.dependencies.items():
                key = f"{package}@{version}"
                if key not in graph:
                    graph[key] = DependencyNode(
                        package_name=package,
                        version=version,
                        repository=repo.name,
                    )
                    
        return graph


class ConflictResolver:
    """Advanced conflict resolution for dependency version conflicts."""
    
    def __init__(self):
        """Initialize resolver."""
        self.resolution_history: list[tuple[DependencyConflict, ResolutionStrategy]] = []
        
    def resolve_conflict(
        self,
        conflict: DependencyConflict,
        strategy: ResolutionStrategy | None = None,
    ) -> str | None:
        """Resolve a dependency conflict using specified or automatic strategy.
        
        Args:
            conflict: The conflict to resolve
            strategy: Resolution strategy (auto-selected if None)
            
        Returns:
            Resolved version or None if unresolvable
        """
        if strategy is None:
            strategy = self._select_strategy(conflict)
            
        resolved_version: str | None = None
        
        if strategy == ResolutionStrategy.HIGHEST_VERSION:
            resolved_version = self._resolve_highest_version(conflict)
        elif strategy == ResolutionStrategy.LOWEST_COMPATIBLE:
            resolved_version = self._resolve_lowest_compatible(conflict)
        elif strategy == ResolutionStrategy.LOCK_TO_STABLE:
            resolved_version = self._resolve_lock_to_stable(conflict)
        elif strategy == ResolutionStrategy.BACKTRACK:
            resolved_version = self._resolve_with_backtracking(conflict)
            
        if resolved_version:
            conflict.recommended_version = resolved_version
            conflict.resolution_strategy = strategy
            conflict.is_resolvable = True
            self.resolution_history.append((conflict, strategy))
            
        return resolved_version
        
    def _select_strategy(self, conflict: DependencyConflict) -> ResolutionStrategy:
        """Automatically select best resolution strategy for conflict.
        
        Args:
            conflict: The conflict to analyze
            
        Returns:
            Recommended strategy
        """
        versions = list(conflict.required_versions.values())
        
        # If all versions are close (same major), use highest
        if self._are_versions_compatible(versions):
            return ResolutionStrategy.HIGHEST_VERSION
            
        # If versions span major versions, need more careful resolution
        if self._has_breaking_changes(versions):
            return ResolutionStrategy.BACKTRACK
            
        # Default to lowest compatible
        return ResolutionStrategy.LOWEST_COMPATIBLE
        
    def _resolve_highest_version(self, conflict: DependencyConflict) -> str:
        """Resolve to highest version among conflicting requirements."""
        versions = list(conflict.required_versions.values())
        # Simple string comparison (would need proper version parsing)
        return max(versions)
        
    def _resolve_lowest_compatible(self, conflict: DependencyConflict) -> str:
        """Resolve to lowest version that satisfies all requirements."""
        versions = list(conflict.required_versions.values())
        # Would need proper version range resolution
        return min(versions)
        
    def _resolve_lock_to_stable(self, conflict: DependencyConflict) -> str:
        """Resolve to most recent stable version."""
        versions = list(conflict.required_versions.values())
        # Filter out pre-release versions
        stable_versions = [v for v in versions if not any(
            marker in v for marker in ["a", "b", "rc", "dev"]
        )]
        return max(stable_versions) if stable_versions else max(versions)
        
    def _resolve_with_backtracking(
        self,
        conflict: DependencyConflict,
    ) -> str | None:
        """Use backtracking algorithm to find compatible version.
        
        This is a simplified version. A full implementation would explore
        the full dependency tree.
        """
        # Simplified backtracking
        versions = list(conflict.required_versions.values())
        
        # Try each version in descending order
        for version in sorted(versions, reverse=True):
            # Would check if this version satisfies all transitive deps
            # For now, return first version
            return version
            
        return None
        
    def _are_versions_compatible(self, versions: list[str]) -> bool:
        """Check if versions are likely compatible (same major version)."""
        # Simplified check - would need proper version parsing
        majors = set()
        for v in versions:
            parts = v.split(".")
            if parts:
                majors.add(parts[0])
        return len(majors) == 1
        
    def _has_breaking_changes(self, versions: list[str]) -> bool:
        """Check if versions span breaking changes (different major versions)."""
        majors = set()
        for v in versions:
            parts = v.split(".")
            if parts:
                majors.add(parts[0])
        return len(majors) > 1


@dataclass(slots=True)
class ConflictResolutionPlan:
    """Plan for resolving a set of conflicts."""
    
    conflicts: list[DependencyConflict]
    resolutions: dict[str, str]  # package -> version
    execution_order: list[str]  # Order to apply updates
    estimated_risk: float  # 0-1
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conflicts": [
                {
                    "package": c.package_name,
                    "versions": c.required_versions,
                    "resolution": c.recommended_version,
                    "strategy": c.resolution_strategy.value if c.resolution_strategy else None,
                }
                for c in self.conflicts
            ],
            "resolutions": self.resolutions,
            "execution_order": self.execution_order,
            "estimated_risk": self.estimated_risk,
        }


def create_resolution_plan(
    conflicts: list[DependencyConflict],
    resolver: ConflictResolver | None = None,
) -> ConflictResolutionPlan:
    """Create a comprehensive resolution plan for a set of conflicts.
    
    Args:
        conflicts: List of conflicts to resolve
        resolver: Optional resolver instance (creates new if None)
        
    Returns:
        Complete resolution plan
    """
    if resolver is None:
        resolver = ConflictResolver()
        
    resolutions: dict[str, str] = {}
    
    # Resolve each conflict
    for conflict in conflicts:
        resolved = resolver.resolve_conflict(conflict)
        if resolved:
            resolutions[conflict.package_name] = resolved
            
    # Determine execution order (topological sort would be better)
    execution_order = list(resolutions.keys())
    
    # Estimate overall risk (simplified)
    risk = min(1.0, len(conflicts) * 0.15)
    
    return ConflictResolutionPlan(
        conflicts=conflicts,
        resolutions=resolutions,
        execution_order=execution_order,
        estimated_risk=risk,
    )
