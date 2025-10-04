"""Compatibility shim for prometheus.packaging.offline — delegates to chiron.packaging.offline.

This module maintains backwards compatibility. All packaging functionality
has been moved to the Chiron subsystem.
"""

from chiron.packaging.offline import (
    DEFAULT_CONFIG_PATH,
    DRY_RUN_BRANCH_PLACEHOLDER,
    GIT_CORE_HOOKS_PATH_KEY,
    LOGGER,
    MANIFEST_FILENAME,
    RUN_MANIFEST_FILENAME,
    OfflinePackagingConfig,
    OfflinePackagingOrchestrator,
    PackagingResult,
    load_config,
)

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "DRY_RUN_BRANCH_PLACEHOLDER",
    "GIT_CORE_HOOKS_PATH_KEY",
    "LOGGER",
    "MANIFEST_FILENAME",
    "RUN_MANIFEST_FILENAME",
    "OfflinePackagingConfig",
    "OfflinePackagingOrchestrator",
    "PackagingResult",
    "load_config",
]
