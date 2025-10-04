# Chiron — Packaging, Dependency Management, and Developer Tooling

> **Status**: ✅ **Extraction Complete** (October 2024)
> 
> All Chiron subsystem components have been successfully extracted from Prometheus core,
> with full backwards compatibility maintained via shims. The subsystem is production-ready
> and all features are accessible via both the new `chiron` CLI and legacy `prometheus` commands.

## Overview

Chiron is a subsystem within the Prometheus project that handles all aspects of:

- **Packaging**: Offline deployment preparation, wheelhouse management
- **Dependency Management**: Guard checks, upgrade planning, drift detection, synchronization
- **Remediation**: Automated fixes for packaging and runtime failures
- **Orchestration**: Unified workflow coordination across all capabilities
- **Diagnostics**: Health checks and readiness validation
- **GitHub Integration**: Artifact synchronization and CI/CD support

Chiron is architecturally separate from the core Prometheus event-driven pipeline, allowing
it to evolve independently while maintaining clear module boundaries.

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

**Dependencies**: Poetry, TOML parsers, optional pip-audit

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

# Packaging
python -m chiron package offline --verbose
python -m chiron package offline --only-phase dependencies

# Diagnostics
python -m chiron doctor offline
python -m chiron doctor offline --format json

# Remediation
python -m chiron remediate wheelhouse --scan-logs var/ci-build.log
python -m chiron remediate runtime --error-type import

# Orchestration
python -m chiron orchestrate status
python -m chiron orchestrate full-dependency --auto-upgrade
python -m chiron orchestrate full-packaging --validate
python -m chiron orchestrate sync-remote ./artifacts
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

1. **Plugin System**: Allow third-party extensions
2. **Web UI**: Dashboard for dependency health and packaging status
3. **Auto-Remediation**: Automatic PR creation for dependency updates
4. **Multi-Repo Support**: Manage dependencies across multiple repositories
5. **Telemetry**: Enhanced observability for all Chiron operations
