"""Compatibility shim for scripts.render_preflight_summary — delegates to chiron.deps.preflight_summary.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.deps.preflight_summary import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.deps.preflight_summary import main
    sys.exit(main())
