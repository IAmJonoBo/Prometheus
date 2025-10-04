"""Compatibility shim for the :mod:`prometheus.remediation` package.

This module maintains backwards compatibility. All remediation functionality
has been moved to the Chiron subsystem.
"""

from __future__ import annotations

import importlib
import sys

_PACKAGE = importlib.import_module("chiron.remediation")

WheelhouseRemediator = _PACKAGE.WheelhouseRemediator
parse_missing_wheel_failures = _PACKAGE.parse_missing_wheel_failures
main = _PACKAGE.main
__all__ = [
    "WheelhouseRemediator",
    "parse_missing_wheel_failures",
    "main",
]

if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
