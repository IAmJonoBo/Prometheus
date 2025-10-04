# Chiron Quick Reference

## What is Chiron?

Chiron is the packaging, dependency management, and developer tooling subsystem of Prometheus. It handles everything related to building, deploying, and maintaining the Prometheus codebase—separate from the runtime event-driven pipeline.

## Quick Start

### Via Standalone Chiron CLI

```bash
# Show version
python -m chiron version

# Check dependency status
python -m chiron deps status --json

# Run offline packaging
python -m chiron package offline

# Diagnose packaging readiness
python -m chiron doctor offline

# Orchestrate full workflow
python -m chiron orchestrate full-dependency
```

### Via Prometheus CLI (Backwards Compatible)

```bash
# Still works - delegates to Chiron
prometheus deps status
prometheus offline-package
prometheus offline-doctor
prometheus orchestrate status
```

## Command Categories

### 📦 Packaging (`chiron package`)
- `offline` — Build offline deployment artifacts

### 🏥 Diagnostics (`chiron doctor`)
- `offline` — Validate packaging readiness

### 📊 Dependencies (`chiron deps`)
- `status` — Show aggregated dependency health
- `guard` — Run policy checks on updates
- `upgrade` — Plan dependency upgrades
- `drift` — Detect divergence from contract
- `sync` — Synchronize manifests from contract
- `preflight` — Pre-deployment validation

### 🔧 Remediation (`chiron remediate`)
- `wheelhouse` — Fix missing/broken wheels
- `runtime` — Handle runtime failures

### 🎭 Orchestration (`chiron orchestrate`)
- `status` — Show orchestration state
- `full-dependency` — Complete dependency workflow
- `full-packaging` — Complete packaging workflow
- `sync-remote` — Sync CI artifacts locally

## Module Structure

```
chiron/
├── __init__.py          # Subsystem root
├── __main__.py          # CLI entry point
├── cli.py               # Typer CLI application
├── packaging/           # Offline packaging
│   ├── offline.py       # Main orchestrator
│   └── metadata.py      # Package metadata
├── deps/                # Dependency management
│   ├── status.py        # Status aggregation
│   ├── guard.py         # Policy enforcement
│   ├── planner.py       # Upgrade planning
│   ├── drift.py         # Drift detection
│   ├── sync.py          # Manifest sync
│   └── preflight.py     # Pre-deployment checks
├── remediation/         # Failure remediation
│   ├── __init__.py      # Wheelhouse remediation
│   ├── runtime.py       # Runtime fixes
│   └── github_summary.py # GitHub Actions integration
├── orchestration/       # Workflow coordination
│   └── coordinator.py   # Main orchestrator
└── doctor/              # Diagnostics
    ├── offline.py       # Packaging checks
    └── package_cli.py   # CLI wrapper
```

## Key Concepts

### Separation from Prometheus Pipeline

**Prometheus Pipeline** (Runtime):
- Ingestion → Retrieval → Reasoning → Decision → Execution → Monitoring
- Handles strategy decisions at runtime
- Event-driven architecture

**Chiron** (Build-time):
- Packaging, dependencies, diagnostics, remediation
- Handles development and deployment tooling
- Command-driven architecture

### Backwards Compatibility

All old paths still work via shims:
- `prometheus.packaging` → `chiron.packaging`
- `prometheus.remediation` → `chiron.remediation`
- `scripts.orchestration_coordinator` → `chiron.orchestration`
- `scripts.deps_status` → `chiron.deps.status`

### Integration Points

1. **CLI**: Both `prometheus` and `python -m chiron` work
2. **Imports**: Use `chiron.*` for new code; old imports still work
3. **CI/CD**: No changes needed; commands work as before
4. **Documentation**: See `docs/chiron/README.md` for details

## Common Workflows

### Weekly Maintenance
```bash
python -m chiron orchestrate full-dependency --auto-upgrade
python -m chiron orchestrate full-packaging --validate
```

### Pre-Release Checklist
```bash
python -m chiron doctor offline
python -m chiron deps guard --fail-threshold needs-review
python -m chiron package offline
```

### CI Artifact Sync
```bash
gh run download <run-id> -n offline-packaging-suite
python -m chiron orchestrate sync-remote ./offline-packaging-suite
```

### Dependency Health Check
```bash
python -m chiron deps status --json
python -m chiron deps drift
python -m chiron deps preflight
```

## Migration Guide

### Old Code
```python
from prometheus.packaging import OfflinePackagingOrchestrator
from scripts.orchestration_coordinator import OrchestrationCoordinator
from scripts.deps_status import generate_status
```

### New Code
```python
from chiron.packaging import OfflinePackagingOrchestrator
from chiron.orchestration import OrchestrationCoordinator
from chiron.deps.status import generate_status
```

### Transitional (Both Work)
Old imports work via compatibility shims, but new code should use `chiron.*` paths.

## Further Reading

- [Chiron README](chiron/README.md) — Complete subsystem documentation
- [Module Boundaries](module-boundaries.md) — System-wide architecture
- [Packaging Workflow Integration](packaging-workflow-integration.md) — Detailed workflows
- [cibuildwheel Integration](cibuildwheel-integration.md) — CI/CD details

## Support

For issues or questions:
1. Check `python -m chiron orchestrate status` for system state
2. Run `python -m chiron doctor offline` for diagnostics
3. Review logs in `var/` directory
4. See `docs/chiron/README.md` for troubleshooting
