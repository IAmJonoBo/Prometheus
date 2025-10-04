"""Compatibility shim for scripts.offline_doctor — delegates to chiron.doctor.offline.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.doctor.offline import *  # noqa: F403, F401

__all__ = ["main"]

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.doctor.offline import main

    sys.exit(main())
