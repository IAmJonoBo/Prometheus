#!/usr/bin/env python3
"""
Policy engine for dependency governance.

Implements allowlist/denylist, version ceilings, upgrade cadences,
and other governance rules for dependency management.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from packaging.specifiers import SpecifierSet
from packaging.version import Version

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PackagePolicy:
    """Policy for a specific package."""
    
    name: str
    allowed: bool = True
    version_ceiling: str | None = None
    version_floor: str | None = None
    allowed_versions: list[str] = field(default_factory=list)
    blocked_versions: list[str] = field(default_factory=list)
    upgrade_cadence_days: int | None = None
    requires_review: bool = False
    reason: str | None = None


@dataclass(slots=True)
class PolicyViolation:
    """A policy violation."""
    
    package: str
    current_version: str | None
    target_version: str | None
    violation_type: str
    message: str
    severity: Literal["error", "warning", "info"] = "error"


@dataclass(slots=True)
class DependencyPolicy:
    """Complete dependency policy configuration."""
    
    default_allowed: bool = True
    default_upgrade_cadence_days: int | None = None
    max_major_version_jump: int = 1
    require_security_review: bool = True
    allow_pre_releases: bool = False
    
    # Package-specific policies
    allowlist: dict[str, PackagePolicy] = field(default_factory=dict)
    denylist: dict[str, PackagePolicy] = field(default_factory=dict)
    
    # Global constraints
    python_version_requirement: str | None = None
    
    @classmethod
    def from_toml(cls, config_path: Path) -> DependencyPolicy:
        """Load policy from TOML configuration file."""
        if not config_path.exists():
            logger.warning(f"Policy config not found: {config_path}, using defaults")
            return cls()
        
        with config_path.open("rb") as f:
            data = tomllib.load(f)
        
        policy_data = data.get("dependency_policy", {})
        
        # Load default settings
        policy = cls(
            default_allowed=policy_data.get("default_allowed", True),
            default_upgrade_cadence_days=policy_data.get("default_upgrade_cadence_days"),
            max_major_version_jump=policy_data.get("max_major_version_jump", 1),
            require_security_review=policy_data.get("require_security_review", True),
            allow_pre_releases=policy_data.get("allow_pre_releases", False),
            python_version_requirement=policy_data.get("python_version_requirement"),
        )
        
        # Load allowlist
        for pkg_name, pkg_data in policy_data.get("allowlist", {}).items():
            policy.allowlist[pkg_name] = PackagePolicy(
                name=pkg_name,
                allowed=True,
                version_ceiling=pkg_data.get("version_ceiling"),
                version_floor=pkg_data.get("version_floor"),
                allowed_versions=pkg_data.get("allowed_versions", []),
                blocked_versions=pkg_data.get("blocked_versions", []),
                upgrade_cadence_days=pkg_data.get("upgrade_cadence_days"),
                requires_review=pkg_data.get("requires_review", False),
                reason=pkg_data.get("reason"),
            )
        
        # Load denylist
        for pkg_name, pkg_data in policy_data.get("denylist", {}).items():
            policy.denylist[pkg_name] = PackagePolicy(
                name=pkg_name,
                allowed=False,
                reason=pkg_data.get("reason", "Package denied by policy"),
            )
        
        return policy


class PolicyEngine:
    """Evaluate and enforce dependency policies."""
    
    def __init__(self, policy: DependencyPolicy):
        self.policy = policy
        self._last_upgrade_timestamps: dict[str, datetime] = {}
    
    def check_package_allowed(self, package_name: str) -> tuple[bool, str | None]:
        """
        Check if a package is allowed by policy.
        
        Returns:
            Tuple of (allowed, reason)
        """
        # Check denylist first
        if package_name in self.policy.denylist:
            pkg_policy = self.policy.denylist[package_name]
            return False, pkg_policy.reason or "Package in denylist"
        
        # Check allowlist
        if package_name in self.policy.allowlist:
            return True, None
        
        # Use default policy
        if not self.policy.default_allowed:
            return False, "Package not in allowlist and default policy is deny"
        
        return True, None
    
    def check_version_allowed(
        self,
        package_name: str,
        version: str,
    ) -> tuple[bool, str | None]:
        """
        Check if a specific version is allowed by policy.
        
        Returns:
            Tuple of (allowed, reason)
        """
        pkg_policy = self.policy.allowlist.get(package_name)
        if not pkg_policy:
            # No specific policy, allow
            return True, None
        
        try:
            ver = Version(version)
        except Exception as e:
            return False, f"Invalid version: {e}"
        
        # Check blocked versions
        if version in pkg_policy.blocked_versions:
            return False, f"Version {version} is blocked"
        
        # Check allowed versions list
        if pkg_policy.allowed_versions:
            if version not in pkg_policy.allowed_versions:
                return False, f"Version {version} not in allowed versions"
        
        # Check version ceiling
        if pkg_policy.version_ceiling:
            try:
                ceiling = Version(pkg_policy.version_ceiling)
                if ver > ceiling:
                    return False, f"Version exceeds ceiling: {pkg_policy.version_ceiling}"
            except Exception:
                pass
        
        # Check version floor
        if pkg_policy.version_floor:
            try:
                floor = Version(pkg_policy.version_floor)
                if ver < floor:
                    return False, f"Version below floor: {pkg_policy.version_floor}"
            except Exception:
                pass
        
        # Check pre-release policy
        if ver.is_prerelease and not self.policy.allow_pre_releases:
            return False, "Pre-release versions not allowed"
        
        return True, None
    
    def check_upgrade_allowed(
        self,
        package_name: str,
        current_version: str,
        target_version: str,
    ) -> list[PolicyViolation]:
        """
        Check if an upgrade is allowed by policy.
        
        Returns:
            List of policy violations (empty if allowed)
        """
        violations: list[PolicyViolation] = []
        
        # Check package allowed
        allowed, reason = self.check_package_allowed(package_name)
        if not allowed:
            violations.append(PolicyViolation(
                package=package_name,
                current_version=current_version,
                target_version=target_version,
                violation_type="package_denied",
                message=reason or "Package denied by policy",
                severity="error",
            ))
            return violations
        
        # Check target version allowed
        allowed, reason = self.check_version_allowed(package_name, target_version)
        if not allowed:
            violations.append(PolicyViolation(
                package=package_name,
                current_version=current_version,
                target_version=target_version,
                violation_type="version_denied",
                message=reason or "Version denied by policy",
                severity="error",
            ))
        
        # Check major version jump
        try:
            current = Version(current_version)
            target = Version(target_version)
            
            if target.major > current.major:
                major_jump = target.major - current.major
                if major_jump > self.policy.max_major_version_jump:
                    violations.append(PolicyViolation(
                        package=package_name,
                        current_version=current_version,
                        target_version=target_version,
                        violation_type="major_version_jump",
                        message=f"Major version jump ({major_jump}) exceeds policy limit ({self.policy.max_major_version_jump})",
                        severity="warning",
                    ))
        except Exception:
            pass
        
        # Check upgrade cadence
        pkg_policy = self.policy.allowlist.get(package_name)
        cadence = pkg_policy.upgrade_cadence_days if pkg_policy else self.policy.default_upgrade_cadence_days
        
        if cadence:
            last_upgrade = self._last_upgrade_timestamps.get(package_name)
            if last_upgrade:
                elapsed = datetime.now(UTC) - last_upgrade
                if elapsed < timedelta(days=cadence):
                    violations.append(PolicyViolation(
                        package=package_name,
                        current_version=current_version,
                        target_version=target_version,
                        violation_type="upgrade_cadence",
                        message=f"Upgrade cadence not met: {elapsed.days}/{cadence} days",
                        severity="warning",
                    ))
        
        # Check if review required
        if pkg_policy and pkg_policy.requires_review:
            violations.append(PolicyViolation(
                package=package_name,
                current_version=current_version,
                target_version=target_version,
                violation_type="review_required",
                message="Package requires manual review before upgrade",
                severity="info",
            ))
        
        return violations
    
    def record_upgrade(self, package_name: str) -> None:
        """Record that an upgrade was performed."""
        self._last_upgrade_timestamps[package_name] = datetime.now(UTC)


def load_policy(config_path: Path | None = None) -> DependencyPolicy:
    """
    Load dependency policy from configuration file.
    
    Args:
        config_path: Path to policy config (defaults to configs/dependency-policy.toml)
    
    Returns:
        DependencyPolicy object
    """
    if config_path is None:
        config_path = Path("configs/dependency-policy.toml")
    
    return DependencyPolicy.from_toml(config_path)
