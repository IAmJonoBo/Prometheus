#!/usr/bin/env python3
"""
Intelligent upgrade advisor for automatic dependency management.

This module provides automatic upgrade recommendations based on:
- Security advisories and CVE data
- Package stability and community adoption
- Mirror availability and compatibility
- Breaking change detection
- Conflict resolution strategies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from chiron.deps import drift as dependency_drift

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class UpgradeRecommendation:
    """Recommendation for a specific package upgrade."""
    
    package: str
    current_version: str | None
    recommended_version: str | None
    priority: Literal["critical", "high", "medium", "low"]
    confidence: float
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    mitigation_steps: list[str] = field(default_factory=list)
    auto_apply_safe: bool = False
    estimated_impact: str = "low"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "package": self.package,
            "current_version": self.current_version,
            "recommended_version": self.recommended_version,
            "priority": self.priority,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "risks": list(self.risks),
            "mitigation_steps": list(self.mitigation_steps),
            "auto_apply_safe": self.auto_apply_safe,
            "estimated_impact": self.estimated_impact,
        }


@dataclass(slots=True)
class UpgradeAdvice:
    """Complete upgrade advice for the dependency set."""
    
    generated_at: datetime
    recommendations: list[UpgradeRecommendation]
    safe_to_auto_apply: list[str]
    requires_review: list[str]
    blocked: list[str]
    summary: dict[str, int]
    mirror_updates_needed: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "recommendations": [rec.to_dict() for rec in self.recommendations],
            "safe_to_auto_apply": list(self.safe_to_auto_apply),
            "requires_review": list(self.requires_review),
            "blocked": list(self.blocked),
            "summary": dict(self.summary),
            "mirror_updates_needed": self.mirror_updates_needed,
        }


class UpgradeAdvisor:
    """
    Intelligent upgrade advisor for dependency management.
    
    Analyzes drift reports, security advisories, and mirror status to provide
    automatic upgrade recommendations with confidence scoring.
    """
    
    def __init__(
        self,
        mirror_root: Path | None = None,
        conservative: bool = True,
        security_first: bool = True,
    ):
        """
        Initialize upgrade advisor.
        
        Args:
            mirror_root: Path to dependency mirror for availability checks
            conservative: If True, only recommend thoroughly tested upgrades
            security_first: Prioritize security patches over features
        """
        self.mirror_root = mirror_root
        self.conservative = conservative
        self.security_first = security_first
    
    def generate_advice(
        self,
        drift_packages: list[dependency_drift.PackageDrift],
        metadata: dict[str, Any] | None = None,
    ) -> UpgradeAdvice:
        """
        Generate comprehensive upgrade advice.
        
        Args:
            drift_packages: List of packages with detected drift
            metadata: Additional metadata about packages (PyPI stats, etc.)
        
        Returns:
            UpgradeAdvice with categorized recommendations
        """
        logger.info("Generating upgrade advice...")
        
        recommendations: list[UpgradeRecommendation] = []
        safe_to_auto_apply: list[str] = []
        requires_review: list[str] = []
        blocked: list[str] = []
        
        for package in drift_packages:
            recommendation = self._analyze_package(package, metadata or {})
            if recommendation:
                recommendations.append(recommendation)
                
                # Categorize based on recommendation
                if recommendation.auto_apply_safe:
                    safe_to_auto_apply.append(recommendation.package)
                elif recommendation.priority in ("critical", "high"):
                    requires_review.append(recommendation.package)
                elif recommendation.priority == "medium":
                    requires_review.append(recommendation.package)
                else:
                    # Low priority can be deferred
                    pass
        
        # Check if mirror updates are needed
        mirror_updates = self._check_mirror_updates_needed(recommendations)
        
        summary = {
            "total": len(recommendations),
            "critical": sum(1 for r in recommendations if r.priority == "critical"),
            "high": sum(1 for r in recommendations if r.priority == "high"),
            "medium": sum(1 for r in recommendations if r.priority == "medium"),
            "low": sum(1 for r in recommendations if r.priority == "low"),
            "auto_apply": len(safe_to_auto_apply),
            "review": len(requires_review),
            "blocked": len(blocked),
        }
        
        return UpgradeAdvice(
            generated_at=datetime.now(UTC),
            recommendations=recommendations,
            safe_to_auto_apply=safe_to_auto_apply,
            requires_review=requires_review,
            blocked=blocked,
            summary=summary,
            mirror_updates_needed=mirror_updates,
        )
    
    def _analyze_package(
        self,
        package: dependency_drift.PackageDrift,
        metadata: dict[str, Any],
    ) -> UpgradeRecommendation | None:
        """Analyze a single package and generate recommendation."""
        if not package.name or not package.latest:
            return None
        
        priority = self._determine_priority(package)
        confidence = self._calculate_confidence(package, metadata)
        reasons = self._gather_reasons(package)
        risks = self._identify_risks(package)
        mitigation = self._suggest_mitigation(package, risks)
        auto_safe = self._is_auto_apply_safe(package, confidence, risks)
        impact = self._estimate_impact(package)
        
        return UpgradeRecommendation(
            package=package.name,
            current_version=package.current,
            recommended_version=package.latest,
            priority=priority,
            confidence=confidence,
            reasons=reasons,
            risks=risks,
            mitigation_steps=mitigation,
            auto_apply_safe=auto_safe,
            estimated_impact=impact,
        )
    
    def _determine_priority(
        self,
        package: dependency_drift.PackageDrift,
    ) -> Literal["critical", "high", "medium", "low"]:
        """Determine upgrade priority based on severity and other factors."""
        severity = package.severity
        
        # Security-related keywords in notes indicate critical priority
        notes_text = " ".join(package.notes).lower()
        if any(kw in notes_text for kw in ["security", "cve", "vulnerability"]):
            return "critical"
        
        # Map severity to priority
        if severity == dependency_drift.RISK_MAJOR:
            # Major versions are high priority but not critical (breaking changes)
            return "high" if self.security_first else "medium"
        elif severity == dependency_drift.RISK_MINOR:
            return "medium"
        elif severity == dependency_drift.RISK_PATCH:
            # Patches are medium priority if security-first, otherwise low
            return "medium" if self.security_first else "low"
        
        return "low"
    
    def _calculate_confidence(
        self,
        package: dependency_drift.PackageDrift,
        metadata: dict[str, Any],
    ) -> float:
        """Calculate confidence score for the upgrade recommendation."""
        confidence = 0.5  # Base confidence
        
        # Boost confidence for patch versions
        if package.severity == dependency_drift.RISK_PATCH:
            confidence += 0.3
        
        # Reduce confidence for major versions
        if package.severity == dependency_drift.RISK_MAJOR:
            confidence -= 0.2
        
        # Adjust based on package popularity/stability (if available in metadata)
        pkg_meta = metadata.get(package.name, {})
        if pkg_meta.get("download_count", 0) > 1000000:
            confidence += 0.1  # Popular packages are more trustworthy
        
        # Check for version age (if available)
        version_age_days = pkg_meta.get("version_age_days", 0)
        if version_age_days > 90:
            confidence += 0.1  # Mature versions are more stable
        elif version_age_days < 7:
            confidence -= 0.15  # Very new versions may have issues
        
        # Clamp to valid range
        return max(0.0, min(1.0, confidence))
    
    def _gather_reasons(self, package: dependency_drift.PackageDrift) -> list[str]:
        """Gather reasons why this upgrade is recommended."""
        reasons: list[str] = []
        
        if package.severity == dependency_drift.RISK_PATCH:
            reasons.append("Patch-level update with bug fixes")
        elif package.severity == dependency_drift.RISK_MINOR:
            reasons.append("Minor version update with new features")
        elif package.severity == dependency_drift.RISK_MAJOR:
            reasons.append("Major version update with potential breaking changes")
        
        for note in package.notes:
            if "security" in note.lower() or "cve" in note.lower():
                reasons.append(f"Security update: {note}")
            elif "deprecated" in note.lower():
                reasons.append(f"Version deprecation: {note}")
        
        return reasons
    
    def _identify_risks(self, package: dependency_drift.PackageDrift) -> list[str]:
        """Identify potential risks of the upgrade."""
        risks: list[str] = []
        
        if package.severity == dependency_drift.RISK_MAJOR:
            risks.append("Breaking API changes possible")
            risks.append("May require code changes")
        
        if package.severity == dependency_drift.RISK_MINOR:
            risks.append("New features may change behavior")
        
        # Check for conflict indicators in notes
        for note in package.notes:
            if "conflict" in note.lower():
                risks.append(f"Dependency conflict: {note}")
        
        return risks
    
    def _suggest_mitigation(
        self,
        package: dependency_drift.PackageDrift,
        risks: list[str],
    ) -> list[str]:
        """Suggest mitigation steps for identified risks."""
        mitigation: list[str] = []
        
        if any("breaking" in r.lower() for r in risks):
            mitigation.append("Review CHANGELOG for breaking changes")
            mitigation.append("Run full test suite after upgrade")
            mitigation.append("Consider staging deployment first")
        
        if any("conflict" in r.lower() for r in risks):
            mitigation.append("Check dependency tree for conflicts")
            mitigation.append("May need to update related packages")
        
        if package.severity == dependency_drift.RISK_MAJOR:
            mitigation.append("Pin to specific version after testing")
            mitigation.append("Update documentation if API changes")
        
        return mitigation
    
    def _is_auto_apply_safe(
        self,
        package: dependency_drift.PackageDrift,
        confidence: float,
        risks: list[str],
    ) -> bool:
        """Determine if upgrade can be safely auto-applied."""
        # Conservative mode requires higher confidence
        min_confidence = 0.75 if self.conservative else 0.65
        
        # Auto-apply only for patch versions with high confidence
        is_patch = package.severity == dependency_drift.RISK_PATCH
        high_confidence = confidence >= min_confidence
        no_major_risks = not any("breaking" in r.lower() for r in risks)
        
        return is_patch and high_confidence and no_major_risks
    
    def _estimate_impact(self, package: dependency_drift.PackageDrift) -> str:
        """Estimate impact of the upgrade."""
        if package.severity == dependency_drift.RISK_MAJOR:
            return "high"
        elif package.severity == dependency_drift.RISK_MINOR:
            return "medium"
        else:
            return "low"
    
    def _check_mirror_updates_needed(
        self,
        recommendations: list[UpgradeRecommendation],
    ) -> bool:
        """Check if mirror needs updates for recommended packages."""
        if not self.mirror_root or not self.mirror_root.exists():
            return False
        
        # If we have recommendations, mirror likely needs updates
        return len(recommendations) > 0


def generate_upgrade_advice(
    drift_packages: list[dependency_drift.PackageDrift],
    metadata: dict[str, Any] | None = None,
    mirror_root: Path | None = None,
    conservative: bool = True,
    security_first: bool = True,
) -> UpgradeAdvice:
    """
    Generate upgrade advice for dependency set.
    
    Convenience function for creating advisor and generating advice.
    
    Args:
        drift_packages: Packages with drift detected
        metadata: Additional package metadata
        mirror_root: Path to dependency mirror
        conservative: Use conservative upgrade strategy
        security_first: Prioritize security updates
    
    Returns:
        UpgradeAdvice with recommendations
    """
    advisor = UpgradeAdvisor(
        mirror_root=mirror_root,
        conservative=conservative,
        security_first=security_first,
    )
    return advisor.generate_advice(drift_packages, metadata)
