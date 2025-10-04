"""Compatibility shim for scripts.preflight_deps — delegates to chiron.deps.preflight.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.preflight import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys
    from chiron.deps.preflight import main
    sys.exit(main())
