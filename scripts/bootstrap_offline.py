"""Compatibility shim for scripts.bootstrap_offline — delegates to chiron.doctor.bootstrap.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.doctor.bootstrap import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.doctor.bootstrap import main
    sys.exit(main(sys.argv[1:]))
