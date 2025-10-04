"""Compatibility shim for scripts.generate_dependency_graph — delegates to chiron.deps.graph.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.graph import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.deps.graph import main
    sys.exit(main())
