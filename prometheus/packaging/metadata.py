"""Compatibility shim for prometheus.packaging.metadata — delegates to chiron.packaging.metadata.

This module maintains backwards compatibility. All packaging functionality
has been moved to the Chiron subsystem.
"""

from chiron.packaging.metadata import (
    WheelhouseManifest,
    load_wheelhouse_manifest,
    write_wheelhouse_manifest,
)

__all__ = [
    "WheelhouseManifest",
    "load_wheelhouse_manifest",
    "write_wheelhouse_manifest",
]
