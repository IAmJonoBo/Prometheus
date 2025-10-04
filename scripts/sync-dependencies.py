"""Compatibility shim for scripts.sync-dependencies — delegates to chiron.deps.sync.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.sync import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.deps.sync import main
    sys.exit(main())
