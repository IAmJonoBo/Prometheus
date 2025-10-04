"""Compatibility shim for scripts.upgrade_guard — delegates to chiron.deps.guard.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.guard import *  # noqa: F403, F401
