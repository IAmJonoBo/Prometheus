"""Compatibility shim for scripts.dependency_drift — delegates to chiron.deps.drift.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.drift import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.deps.drift import main
    sys.exit(main())
