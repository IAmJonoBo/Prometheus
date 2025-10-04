"""Compatibility shim for scripts.process_dryrun_governance — delegates to chiron.orchestration.governance.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.orchestration.governance import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.orchestration.governance import main

    sys.exit(main())
