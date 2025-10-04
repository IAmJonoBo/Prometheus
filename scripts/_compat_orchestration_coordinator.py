"""Compatibility shim for scripts.orchestration_coordinator.

This module has been moved to chiron.orchestration.coordinator.
This shim maintains backwards compatibility.
"""

from chiron.orchestration.coordinator import *  # noqa: F403, F401

__all__ = [
    "OrchestrationCoordinator",
    "OrchestrationContext",
]
