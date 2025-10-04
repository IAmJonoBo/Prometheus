"""Chiron — Packaging, dependency management, and developer tooling subsystem.

Chiron handles all aspects of dependency management, packaging, offline deployment,
remediation, and GitHub synchronization. It is a separate subsystem from the core
Prometheus event-driven pipeline.

Modules:
- packaging: Offline packaging orchestration and metadata handling
- remediation: Wheelhouse and runtime failure remediation
- orchestration: Unified workflow coordination across all Chiron capabilities
- deps: Dependency management (guard, upgrade, drift, sync, preflight)
- doctor: Diagnostics and health checks
- tools: Developer utilities (YAML formatting, etc.)
- plugins: Plugin system for extensibility
- telemetry: Enhanced observability for Chiron operations
- github: GitHub Actions integration and artifact synchronization
"""

__version__ = "0.1.0"

__all__ = [
    "__version__",
]
