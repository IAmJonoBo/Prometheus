"""Compatibility shim for scripts.deps_status — delegates to chiron.deps.status.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.status import *  # noqa: F403, F401
