"""Chiron deps module — Dependency management and policy enforcement."""

from chiron.deps.status import DependencyStatus, PlannerSettings, generate_status
from chiron.deps.guard import DependencyGuard, GuardCheckResult
from chiron.deps.planner import UpgradePlanner, PlannerResult

__all__ = [
    "DependencyStatus",
    "PlannerSettings",
    "generate_status",
    "DependencyGuard",
    "GuardCheckResult",
    "UpgradePlanner",
    "PlannerResult",
]
