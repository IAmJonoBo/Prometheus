"""Compatibility shim for scripts.deps_status.

This module has been moved to chiron.deps.status.
This shim maintains backwards compatibility.
"""

from chiron.deps.status import *  # noqa: F403, F401

__all__ = [
    "DependencyStatus",
    "PlannerSettings",
    "generate_status",
]
