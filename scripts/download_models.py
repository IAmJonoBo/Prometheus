"""Compatibility shim for scripts.download_models — delegates to chiron.doctor.models.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.doctor.models import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.doctor.models import main

    sys.exit(main(sys.argv[1:]))
