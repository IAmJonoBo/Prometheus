"""Compatibility shim for scripts.format_yaml — delegates to chiron.tools.format_yaml.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.
"""

from chiron.tools.format_yaml import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.tools.format_yaml import main
    sys.exit(main())
