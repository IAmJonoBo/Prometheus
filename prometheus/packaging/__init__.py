"""Compatibility shim for prometheus.packaging — delegates to chiron.packaging.

This module maintains backwards compatibility. All packaging functionality
has been moved to the Chiron subsystem.
"""

from chiron.packaging.offline import (
    OfflinePackagingConfig,
    OfflinePackagingOrchestrator,
    PackagingResult,
    load_config,
)

__all__ = [
    "OfflinePackagingConfig",
    "OfflinePackagingOrchestrator",
    "PackagingResult",
    "load_config",
]
