"""Compatibility shim for scripts.offline_package — delegates to chiron.doctor.package_cli.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.doctor.package_cli import *  # noqa: F403, F401

__all__ = ["main"]

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.doctor.package_cli import main

    sys.exit(main())
