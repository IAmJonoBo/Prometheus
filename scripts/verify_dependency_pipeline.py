"""Compatibility shim for scripts.verify_dependency_pipeline — delegates to chiron.deps.verify.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.verify import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.deps.verify import main

    sys.exit(main())
