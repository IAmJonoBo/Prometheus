"""Compatibility shim for scripts.bootstrap_offline — delegates to chiron.doctor.bootstrap.

This module has been moved to the Chiron subsystem.
This shim maintains backwards compatibility.

.. deprecated:: 0.1.0
   Use `chiron.doctor.bootstrap` instead. This compatibility shim will be removed
   in a future version.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "scripts.bootstrap_offline is deprecated. Use 'chiron.doctor.bootstrap' instead. "
    "This compatibility shim will be removed in version 2.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

from chiron.doctor.bootstrap import *  # noqa: F403, F401

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys

    from chiron.doctor.bootstrap import main
    sys.exit(main(sys.argv[1:]))
