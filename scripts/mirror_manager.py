"""Compatibility shim for scripts.mirror_manager — delegates to chiron.deps.mirror_manager.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.mirror_manager import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys
    from chiron.deps.mirror_manager import main
    sys.exit(main())
