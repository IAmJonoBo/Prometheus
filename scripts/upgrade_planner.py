"""Compatibility shim for scripts.upgrade_planner — delegates to chiron.deps.planner.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.planner import *  # noqa: F403, F401
