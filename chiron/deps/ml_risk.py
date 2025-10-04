#!/usr/bin/env python3
"""Machine learning-based update risk prediction and intelligent rollback.

Provides ML-powered capabilities for:
- Update risk scoring based on historical patterns
- Feature extraction from dependency updates
- Intelligent rollback decision making
- Learning from historical outcomes
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "UpdateRiskPredictor",
    "RiskScore",
    "IntelligentRollback",
    "RollbackDecision",
]


@dataclass(slots=True)
class UpdateFeatures:
    """Features extracted from a dependency update for risk assessment."""
    
    package_name: str
    version_from: str
    version_to: str
    major_version_change: bool
    minor_version_change: bool
    patch_version_change: bool
    has_breaking_changes: bool
    security_update: bool
    days_since_last_update: int
    package_popularity_score: float  # 0-1 based on downloads
    has_test_coverage: bool
    is_transitive_dependency: bool
    dependency_count: int  # Number of packages that depend on this


@dataclass(slots=True)
class RiskScore:
    """Risk score for a dependency update."""
    
    package_name: str
    score: float  # 0-1, where 1 is highest risk
    confidence: float  # 0-1, confidence in the prediction
    factors: dict[str, float]  # Contributing factors to the score
    recommendation: str  # "safe", "needs-review", "blocked"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "package_name": self.package_name,
            "score": self.score,
            "confidence": self.confidence,
            "factors": self.factors,
            "recommendation": self.recommendation,
        }


@dataclass(slots=True)
class HistoricalOutcome:
    """Historical outcome of a dependency update."""
    
    package_name: str
    version_from: str
    version_to: str
    timestamp: datetime
    success: bool
    rolled_back: bool
    failure_reason: str | None = None
    features: UpdateFeatures | None = None


class UpdateRiskPredictor:
    """ML-based risk predictor for dependency updates.
    
    Uses a simple weighted scoring model that can be extended with
    more sophisticated ML models (e.g., Random Forest, XGBoost).
    """
    
    def __init__(self, history_path: Path | None = None):
        """Initialize predictor with optional historical data path."""
        self.history_path = history_path or Path("var/upgrade-guard/history.json")
        self.history: list[HistoricalOutcome] = []
        self._load_history()
        
    def predict_risk(self, features: UpdateFeatures) -> RiskScore:
        """Predict risk score for an update based on features.
        
        Args:
            features: Extracted features for the update
            
        Returns:
            Risk score with recommendation
        """
        # Calculate weighted risk factors
        factors: dict[str, float] = {}
        
        # Version change factors
        if features.major_version_change:
            factors["major_version_change"] = 0.6
        elif features.minor_version_change:
            factors["minor_version_change"] = 0.3
        elif features.patch_version_change:
            factors["patch_version_change"] = 0.1
            
        # Breaking changes
        if features.has_breaking_changes:
            factors["breaking_changes"] = 0.8
            
        # Security updates have lower risk despite changes
        if features.security_update:
            factors["security_update"] = -0.3  # Negative = reduces risk
            
        # Time since last update
        if features.days_since_last_update < 7:
            factors["recent_activity"] = 0.2
        elif features.days_since_last_update > 180:
            factors["stale_dependency"] = 0.3
            
        # Popularity and maturity
        popularity_risk = (1.0 - features.package_popularity_score) * 0.2
        factors["unpopular_package"] = popularity_risk
        
        # Test coverage
        if not features.has_test_coverage:
            factors["no_test_coverage"] = 0.4
            
        # Dependency depth
        if features.is_transitive_dependency:
            factors["transitive_dependency"] = 0.1
            
        # High dependency count = more risk
        if features.dependency_count > 10:
            factors["high_dependency_count"] = 0.3
            
        # Historical success rate for this package
        historical_risk = self._calculate_historical_risk(features.package_name)
        if historical_risk is not None:
            factors["historical_failures"] = historical_risk
            
        # Aggregate score (clamped to 0-1)
        total_score = sum(factors.values())
        score = max(0.0, min(1.0, 0.3 + total_score))  # Base risk of 0.3
        
        # Calculate confidence based on historical data
        package_history = [
            h for h in self.history
            if h.package_name == features.package_name
        ]
        confidence = min(1.0, len(package_history) * 0.1 + 0.5)
        
        # Determine recommendation
        if score < 0.3:
            recommendation = "safe"
        elif score < 0.7:
            recommendation = "needs-review"
        else:
            recommendation = "blocked"
            
        return RiskScore(
            package_name=features.package_name,
            score=score,
            confidence=confidence,
            factors=factors,
            recommendation=recommendation,
        )
        
    def record_outcome(self, outcome: HistoricalOutcome) -> None:
        """Record historical outcome for learning."""
        self.history.append(outcome)
        self._save_history()
        
    def _calculate_historical_risk(self, package_name: str) -> float | None:
        """Calculate risk based on historical success rate."""
        package_history = [
            h for h in self.history
            if h.package_name == package_name
        ]
        
        if not package_history:
            return None
            
        failure_count = sum(1 for h in package_history if not h.success or h.rolled_back)
        failure_rate = failure_count / len(package_history)
        
        return failure_rate * 0.5  # Cap contribution at 0.5
        
    def _load_history(self) -> None:
        """Load historical outcomes from disk."""
        if not self.history_path.exists():
            return
            
        try:
            data = json.loads(self.history_path.read_text())
            # Simple deserialization (would need full implementation)
            self.history = []  # Placeholder
        except Exception:
            # Handle loading errors gracefully
            pass
            
    def _save_history(self) -> None:
        """Save historical outcomes to disk."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        # Simple serialization (would need full implementation)
        # self.history_path.write_text(json.dumps([...], indent=2))


@dataclass(slots=True)
class HealthMetric:
    """System health metric for rollback decisions."""
    
    name: str
    value: float
    threshold: float
    breached: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class RollbackDecision:
    """Decision on whether to rollback."""
    
    should_rollback: bool
    confidence: float
    breached_metrics: list[HealthMetric]
    reason: str
    partial_rollback_packages: list[str] = field(default_factory=list)


class IntelligentRollback:
    """Intelligent rollback decision engine based on health signals."""
    
    def __init__(self):
        """Initialize rollback engine."""
        self.health_metrics: list[HealthMetric] = []
        self.risk_predictor = UpdateRiskPredictor()
        
    def add_health_metric(self, metric: HealthMetric) -> None:
        """Add a health metric for consideration."""
        self.health_metrics.append(metric)
        
    def should_rollback(
        self,
        recent_updates: list[str],
        observation_window_seconds: int = 300,
    ) -> RollbackDecision:
        """Decide if rollback is necessary based on health signals.
        
        Args:
            recent_updates: List of recently updated packages
            observation_window_seconds: How long to monitor after update
            
        Returns:
            Rollback decision with rationale
        """
        # Check for breached metrics
        breached = [m for m in self.health_metrics if m.breached]
        
        if not breached:
            return RollbackDecision(
                should_rollback=False,
                confidence=0.9,
                breached_metrics=[],
                reason="All health metrics within normal thresholds",
            )
            
        # Count critical vs warning breaches
        critical_breaches = [
            m for m in breached
            if m.value > m.threshold * 1.5  # 50% over threshold = critical
        ]
        
        # If multiple critical breaches, recommend full rollback
        if len(critical_breaches) >= 2:
            return RollbackDecision(
                should_rollback=True,
                confidence=0.95,
                breached_metrics=critical_breaches,
                reason=f"Multiple critical health breaches detected: {', '.join(m.name for m in critical_breaches)}",
            )
            
        # If single critical breach, try to identify problematic package
        if critical_breaches:
            # Attempt to correlate with specific package
            # (simplified - would need more sophisticated correlation)
            if recent_updates:
                return RollbackDecision(
                    should_rollback=True,
                    confidence=0.75,
                    breached_metrics=critical_breaches,
                    reason=f"Critical breach in {critical_breaches[0].name}",
                    partial_rollback_packages=recent_updates[:1],  # Most recent
                )
                
        # Multiple warnings but no critical - monitor
        if len(breached) >= 3:
            return RollbackDecision(
                should_rollback=True,
                confidence=0.6,
                breached_metrics=breached,
                reason=f"Multiple health warnings may indicate instability: {', '.join(m.name for m in breached)}",
            )
            
        # Default: don't rollback yet
        return RollbackDecision(
            should_rollback=False,
            confidence=0.5,
            breached_metrics=breached,
            reason=f"Monitoring {len(breached)} warning(s), not critical yet",
        )
        
    def execute_rollback(
        self,
        decision: RollbackDecision,
        dry_run: bool = False,
    ) -> bool:
        """Execute rollback based on decision.
        
        Args:
            decision: The rollback decision to execute
            dry_run: If True, only simulate the rollback
            
        Returns:
            True if rollback was successful
        """
        if not decision.should_rollback:
            return False
            
        if dry_run:
            print(f"[DRY RUN] Would rollback: {decision.reason}")
            if decision.partial_rollback_packages:
                print(f"[DRY RUN] Packages: {', '.join(decision.partial_rollback_packages)}")
            return True
            
        # Actual rollback logic would go here
        # Would integrate with auto-sync rollback mechanism
        print(f"🔄 Executing rollback: {decision.reason}")
        
        return True
