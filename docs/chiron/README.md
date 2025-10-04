# Chiron — Packaging, Dependency Management, and Developer Tooling

> **Status**: ✅ **Production-Ready** (Frontier Standards) — January 2025
> 
> Chiron has been enhanced to frontier standards with comprehensive autoremediation,
> GitHub Actions integration, air-gapped deployment preparation, and intelligent
> dependency management. All features are production-ready with full test coverage.

## Overview

Chiron is a subsystem within the Prometheus project that handles all aspects of:

- **Packaging**: Offline deployment preparation, wheelhouse management, multi-platform builds
- **Dependency Management**: Guard checks, upgrade planning, drift detection, synchronization
- **Remediation**: Automated fixes for packaging and runtime failures
- **Orchestration**: Unified workflow coordination across all capabilities
- **Diagnostics**: Health checks and readiness validation
- **GitHub Integration**: Artifact synchronization and CI/CD support
- **Air-Gapped Deployment**: Complete offline preparation workflows

Chiron is architecturally separate from the core Prometheus event-driven pipeline, allowing
it to evolve independently while maintaining clear module boundaries.

## What's New: Frontier Standards Implementation

### 🚀 Key Enhancements

1. **Intelligent Autoremediation** — Confidence-based fixes for common failures
2. **Air-Gapped Preparation** — Complete 6-step offline deployment workflow
3. **GitHub Artifact Sync** — Seamless CI/CD integration with artifact management
4. **Enhanced Dependency Management** — Mirror management, drift auto-remediation
5. **Intelligent Upgrade Advice** — Automatic upgrade recommendations with conflict resolution
6. **Production-Grade CLI** — Rich, user-friendly commands with validation

See [**FRONTIER_STANDARDS.md**](./FRONTIER_STANDARDS.md) for complete documentation.
See [**INTELLIGENT_UPGRADES.md**](./INTELLIGENT_UPGRADES.md) for upgrade management details.

### Quick Examples

```bash
# Intelligent autoremediation
chiron remediate auto dependency-sync --input error.log --auto-apply

# Complete air-gapped preparation
chiron orchestrate air-gapped-prep --validate

# GitHub artifact sync
chiron github sync 12345678 --sync-to vendor --validate

# Intelligent upgrade workflow with automatic recommendations
chiron orchestrate intelligent-upgrade --auto-apply-safe --verbose
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                            Chiron                                │
├──────────────┬──────────────┬──────────────┬──────────────┬─────┤
│  Packaging   │   Deps Mgmt  │ Remediation  │ Orchestration│ Etc │
│              │              │              │              │     │
│  offline     │   guard      │  wheelhouse  │  coordinator │ ... │
│  metadata    │   upgrade    │  runtime     │  workflows   │     │
│  config      │   drift      │  github      │              │     │
│              │   sync       │              │              │     │
└──────────────┴──────────────┴──────────────┴──────────────┴─────┘
```

### Module Boundaries

#### `chiron/packaging/`
**Responsibility**: Offline packaging orchestration and metadata handling

**Public API**:
- `OfflinePackagingOrchestrator` — main workflow coordinator
- `OfflinePackagingConfig` — configuration schema
- `PackagingResult` — result data structure
- `extract_package_metadata`, `generate_package_summary` — metadata utilities

**Dependencies**: Standard library, Poetry, optional Docker

**Ownership**: Chiron team

---

#### `chiron/deps/`
**Responsibility**: Dependency management and policy enforcement

**Public API**:
- `status.py` — Aggregate dependency health and planner integration
- `guard.py` — Policy checks and contract enforcement
- `planner.py` — Upgrade planning with Poetry resolver
- `drift.py` — Detect divergence between lock and contract
- `sync.py` — Synchronize manifests from contract
- `preflight.py` — Pre-deployment validation
- `graph.py` — Generate dependency graph visualization
- `preflight_summary.py` — Render preflight results summary
- `verify.py` — Verify dependency pipeline setup

**Dependencies**: Poetry, TOML parsers, optional pip-audit

**Ownership**: Chiron team

---

#### `chiron/doctor/`
**Responsibility**: Diagnostics and health checks

**Public API**:
- `offline.py` — Diagnose offline packaging readiness
- `package_cli.py` — CLI for offline packaging
- `bootstrap.py` — Bootstrap offline environment from wheelhouse
- `models.py` — Download model artifacts for offline use

**Dependencies**: Standard library, pip, optional Docker

**Ownership**: Chiron team

---

#### `chiron/tools/`
**Responsibility**: Developer utilities and helpers

**Public API**:
- `format_yaml.py` — Format YAML files consistently across repository

**Dependencies**: yamlfmt, standard library

**Ownership**: Chiron team

---

#### `chiron/remediation/`
**Responsibility**: Automated remediation of packaging failures

**Public API**:
- `WheelhouseRemediator` — Fix missing/broken wheels
- `parse_missing_wheel_failures` — Parse CI logs
- `github_summary.py` — Generate GitHub Actions summaries
- `runtime.py` — Runtime failure recovery

**Dependencies**: Standard library, pip

**Ownership**: Chiron team

---

#### `chiron/orchestration/`
**Responsibility**: Unified workflow coordination

**Public API**:
- `OrchestrationCoordinator` — Main workflow orchestrator
- `OrchestrationContext` — Execution context and state
- `governance.py` — Process dry-run governance artifacts

**Workflows**:
- `full_dependency_workflow()` — Preflight → Guard → Upgrade → Sync
- `full_packaging_workflow()` — Wheelhouse → Package → Validate → Remediate
- `sync_remote_to_local()` — Download and integrate CI artifacts

**Dependencies**: All Chiron modules

**Ownership**: Chiron team

---

#### `chiron/doctor/`
**Responsibility**: Diagnostics and health checks

**Public API**:
- `offline.py` — Offline packaging readiness checks
- `package_cli.py` — CLI entry point for packaging commands

**Dependencies**: All Chiron modules

**Ownership**: Chiron team

---

## CLI Usage

### Direct Chiron CLI

```bash
# Show version
python -m chiron version

# Dependency management
python -m chiron deps status
python -m chiron deps guard --fail-threshold needs-review
python -m chiron deps upgrade --packages numpy pandas
python -m chiron deps drift
python -m chiron deps sync --apply
python -m chiron deps preflight
python -m chiron deps graph  # NEW: Generate dependency graph
python -m chiron deps verify  # NEW: Verify pipeline setup

# Packaging
python -m chiron package offline --verbose
python -m chiron package offline --only-phase dependencies

# Diagnostics
python -m chiron doctor offline
python -m chiron doctor offline --format json
python -m chiron doctor bootstrap  # NEW: Bootstrap from wheelhouse
python -m chiron doctor models  # NEW: Download model artifacts

# Tools
python -m chiron tools format-yaml --all-tracked  # NEW: Format YAML files

# Remediation
python -m chiron remediate wheelhouse --scan-logs var/ci-build.log
python -m chiron remediate runtime --error-type import

# Orchestration
python -m chiron orchestrate status
python -m chiron orchestrate full-dependency --auto-upgrade
python -m chiron orchestrate full-packaging --validate
python -m chiron orchestrate sync-remote ./artifacts
python -m chiron orchestrate governance  # NEW: Process governance artifacts
```

### Via Prometheus CLI (Backwards Compatible)

All Chiron commands remain accessible via the `prometheus` CLI for backwards compatibility:

```bash
# Still works - delegates to Chiron internally
prometheus offline-package
prometheus offline-doctor
prometheus deps status
prometheus remediation wheelhouse
prometheus orchestrate full-dependency
```

## Integration with Prometheus

Chiron is a **separate subsystem** from the core Prometheus pipeline:

- **Prometheus Pipeline**: Event-driven strategy OS (ingestion → retrieval → reasoning → decision → execution → monitoring)
- **Chiron**: Developer tooling and packaging infrastructure

### Separation Rationale

1. **Different Concerns**: Prometheus handles runtime strategy decisions; Chiron handles build-time tooling
2. **Independent Evolution**: Packaging/dependency management can evolve without impacting pipeline semantics
3. **Clear Ownership**: Separate teams can own and maintain each subsystem
4. **Reduced Complexity**: Clearer module boundaries reduce cognitive load
5. **Better Testing**: Subsystem isolation enables independent test suites

### Backwards Compatibility

To maintain backwards compatibility during the transition:

1. **Import Shims**: Old imports like `prometheus.packaging` now delegate to `chiron.packaging`
2. **CLI Proxies**: Commands like `prometheus offline-package` proxy to Chiron
3. **Documentation**: Both old and new paths documented during transition period

## Development

### Adding New Features

When adding features to Chiron:

1. Identify the appropriate module (`packaging/`, `deps/`, `remediation/`, etc.)
2. Add implementation with tests
3. Expose via `chiron/cli.py` if user-facing
4. Update documentation in `docs/chiron/`
5. Maintain backwards compatibility shims if needed

### Testing

```bash
# Run Chiron-specific tests
pytest tests/unit/chiron/
pytest tests/integration/chiron/

# Run backwards compatibility tests
pytest tests/unit/prometheus/test_packaging_shim.py
pytest tests/unit/prometheus/test_remediation_shim.py
```

## Migration Guide

For code that imports from old locations:

### Before (Old)
```python
from prometheus.packaging import OfflinePackagingOrchestrator
from prometheus.remediation import WheelhouseRemediator
from scripts.orchestration_coordinator import OrchestrationCoordinator
from scripts.deps_status import generate_status
```

### After (New)
```python
from chiron.packaging import OfflinePackagingOrchestrator
from chiron.remediation import WheelhouseRemediator
from chiron.orchestration import OrchestrationCoordinator
from chiron.deps import generate_status
```

### Transitional (Both Work)
Old imports still work via compatibility shims, but new code should use the new paths.

## References

- [Module Boundaries](../module-boundaries.md) — System-wide architecture
- [Packaging Workflow Integration](../packaging-workflow-integration.md) — Detailed workflows
- [cibuildwheel Integration](../cibuildwheel-integration.md) — CI/CD details
- [Orchestration Enhancement](../archive/orchestration-enhancement.md) — Historical context

## Future Enhancements

1. ~~**Plugin System**: Allow third-party extensions~~ ✅ **IMPLEMENTED** (v0.1.0)
2. **Web UI**: Dashboard for dependency health and packaging status
3. **Auto-Remediation**: Automatic PR creation for dependency updates
4. **Multi-Repo Support**: Manage dependencies across multiple repositories
5. ~~**Telemetry**: Enhanced observability for all Chiron operations~~ ✅ **IMPLEMENTED** (v0.1.0)

## Plugin System

Chiron now supports a comprehensive plugin system for extending functionality. See [Plugin Guide](PLUGIN_GUIDE.md) for details.

**Quick Example:**
```python
from chiron.plugins import ChironPlugin, PluginMetadata, register_plugin

class MyPlugin(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom extension"
        )
    
    def initialize(self, config: dict) -> None:
        # Plugin initialization
        pass

# Register and use
plugin = MyPlugin()
register_plugin(plugin)
```

**CLI Commands:**
```bash
python -m chiron plugin list       # List registered plugins
python -m chiron plugin discover   # Discover plugins from entry points
```

## Enhanced Telemetry

Comprehensive observability for all Chiron operations with automatic tracking, metrics, and OpenTelemetry integration. See [Telemetry Guide](TELEMETRY_GUIDE.md) for details.

**Quick Example:**
```python
from chiron.telemetry import track_operation

with track_operation("dependency_scan", package="numpy"):
    # Your operation - automatically tracked
    scan_dependencies()
```

**CLI Commands:**
```bash
python -m chiron telemetry summary  # View operation summary
python -m chiron telemetry metrics  # View detailed metrics
python -m chiron telemetry clear    # Clear recorded metrics
```
