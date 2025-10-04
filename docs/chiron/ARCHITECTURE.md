# Chiron Subsystem Architecture

## Before and After Comparison

### Before: Mixed Concerns

```
prometheus/
├── cli.py                    # Monolithic CLI (pipeline + tooling)
├── packaging/                # Build-time tooling in runtime package
│   ├── offline.py
│   └── metadata.py
├── remediation/              # Build-time tooling in runtime package
│   └── ...
└── pipeline stages/          # Runtime event-driven pipeline
    ├── ingestion/
    ├── retrieval/
    ├── reasoning/
    ├── decision/
    ├── execution/
    └── monitoring/

scripts/                      # Scattered tooling
├── orchestration_coordinator.py
├── deps_status.py
├── upgrade_guard.py
├── upgrade_planner.py
├── dependency_drift.py
├── sync-dependencies.py
├── preflight_deps.py
└── offline_doctor.py
```

**Problems**:

- Mixed runtime and build-time concerns
- Unclear module boundaries
- Difficult to test independently
- Poor discoverability
- Maintenance burden

### After: Clear Separation

```
prometheus/
├── cli.py                    # Pipeline CLI (delegates tooling to Chiron)
├── packaging/                # Compatibility shim → chiron.packaging
├── remediation/              # Compatibility shim → chiron.remediation
└── pipeline stages/          # Pure runtime event-driven pipeline
    ├── ingestion/
    ├── retrieval/
    ├── reasoning/
    ├── decision/
    ├── execution/
    └── monitoring/

chiron/                       # ✨ NEW: Developer tooling subsystem
├── cli.py                    # Unified tooling CLI
├── __main__.py               # Entry point: python -m chiron
├── packaging/                # Offline packaging
│   ├── offline.py
│   └── metadata.py
├── remediation/              # Failure remediation
│   ├── __init__.py
│   ├── runtime.py
│   └── github_summary.py
├── deps/                     # Dependency management
│   ├── status.py
│   ├── guard.py
│   ├── planner.py
│   ├── drift.py
│   ├── sync.py
│   ├── preflight.py
│   └── mirror_manager.py
├── orchestration/            # Workflow coordination
│   └── coordinator.py
└── doctor/                   # Diagnostics
    ├── offline.py
    └── package_cli.py

scripts/                      # Compatibility shims
├── _compat_orchestration_coordinator.py
└── _compat_deps_status.py
```

**Benefits**:

- Clear separation of concerns
- Independent evolution
- Better testability
- Improved discoverability
- Reduced coupling

## Architectural Separation

```
┌────────────────────────────────────────────────────────────┐
│                     Prometheus System                       │
├─────────────────────────────┬──────────────────────────────┤
│   Prometheus (Runtime)      │   Chiron (Build-time)        │
│                             │                              │
│  Event-driven pipeline:     │  Command-driven tooling:     │
│  ┌──────────────────────┐  │  ┌──────────────────────┐   │
│  │ Ingestion            │  │  │ Packaging            │   │
│  │   ↓                  │  │  │ Dependency Mgmt      │   │
│  │ Retrieval            │  │  │ Remediation          │   │
│  │   ↓                  │  │  │ Orchestration        │   │
│  │ Reasoning            │  │  │ Diagnostics          │   │
│  │   ↓                  │  │  │ CI/CD Integration    │   │
│  │ Decision             │  │  └──────────────────────┘   │
│  │   ↓                  │  │                              │
│  │ Execution            │  │  Accessible via:             │
│  │   ↓                  │  │  • python -m chiron          │
│  │ Monitoring           │  │  • prometheus (delegates)    │
│  └──────────────────────┘  │                              │
│                             │                              │
│  Accessible via:            │  Focus:                      │
│  • prometheus pipeline      │  • Offline packaging         │
│  • API endpoints            │  • Dependency health         │
│  • SDK                      │  • Build automation          │
│                             │  • Developer workflows       │
│  Focus:                     │                              │
│  • Strategy decisions       │  Independent evolution       │
│  • Evidence-linked actions  │  from pipeline concerns      │
│  • Runtime workflows        │                              │
└─────────────────────────────┴──────────────────────────────┘
         ↓                               ↓
    Shared Infrastructure:
    • observability/
    • common/
    • configs/
```

## Module Dependency Flow

### Allowed Dependencies

```
Prometheus Pipeline Stages
    ↓
common/contracts/  ← Event schemas
    ↑
Monitoring & Observability
    ↑
Chiron Subsystem → Shared infrastructure only
    (No dependencies on pipeline stages)
```

### Forbidden Dependencies

```
Pipeline Stages ❌→ Chiron
    (Runtime must not depend on build tooling)

Chiron ❌→ Pipeline Stages
    (Build tooling must remain independent)
```

## CLI Integration

```
┌─────────────────────────────────────────────────────────┐
│             User Interface                               │
├──────────────────────┬──────────────────────────────────┤
│ prometheus CLI       │  python -m chiron                 │
│                      │                                   │
│ Pipeline commands:   │  Tooling commands:                │
│ • pipeline           │  • deps status                    │
│ • pipeline-dry-run   │  • deps guard                     │
│ • validate-config    │  • deps upgrade                   │
│ • evaluate-rag       │  • package offline                │
│ • temporal           │  • doctor offline                 │
│ • debug              │  • remediate wheelhouse           │
│                      │  • orchestrate full-dependency    │
│ Tooling delegation:  │                                   │
│ • deps → chiron      │  Direct access to Chiron          │
│ • offline-* → chiron │                                   │
│ • orchestrate →chiron│                                   │
│ • remediation →chiron│                                   │
└──────────────────────┴──────────────────────────────────┘
```

## Import Paths

### Old Paths (Still Work via Shims)

```python
from prometheus.packaging import OfflinePackagingOrchestrator
from prometheus.remediation import WheelhouseRemediator
from scripts.orchestration_coordinator import OrchestrationCoordinator
from scripts.deps_status import generate_status
from scripts.upgrade_guard import main
```

### New Paths (Recommended)

```python
from chiron.packaging import OfflinePackagingOrchestrator
from chiron.remediation import WheelhouseRemediator
from chiron.orchestration import OrchestrationCoordinator
from chiron.deps.status import generate_status
from chiron.deps.guard import main
```

## Testing Strategy

```
tests/
├── unit/
│   ├── chiron/              # ✨ NEW: Chiron-specific tests
│   │   ├── test_packaging.py
│   │   ├── test_deps.py
│   │   └── test_orchestration.py
│   ├── prometheus/          # Pipeline tests + shim tests
│   │   ├── test_pipeline.py
│   │   ├── test_packaging_shim.py  # Verify shims work
│   │   └── test_remediation_shim.py
│   └── ...
├── integration/
│   ├── chiron/              # ✨ NEW: Chiron integration tests
│   └── ...
└── e2e/
    ├── test_full_pipeline.py
    └── test_full_packaging.py
```

## Evolution Path

### Phase 1: Structure ✅

- Create chiron/ directory
- Copy and organize files
- Fix internal imports
- Create shims

### Phase 2: Documentation ✅

- Write comprehensive docs
- Create quick reference
- Update main docs index
- Write ADR-0004

### Phase 3: Migration (In Progress)

- Update test imports
- Validate CLI commands
- Update CI/CD if needed
- Add pyproject.toml entry

### Phase 4: Stabilization (Future)

- Gradual import migration
- Deprecation warnings
- Remove old paths (major version)

## Benefits Summary

| Aspect            | Before                | After                          |
| ----------------- | --------------------- | ------------------------------ |
| **Boundaries**    | Unclear mix           | Clear separation               |
| **Testing**       | Complex, intertwined  | Independent, focused           |
| **Discovery**     | Scattered across dirs | Unified in chiron/             |
| **Evolution**     | Coupled changes       | Independent evolution          |
| **Ownership**     | Unclear               | Clear subsystem teams          |
| **Documentation** | Fragmented            | Centralized docs/chiron/       |
| **CLI**           | Monolithic            | Modular + backwards compatible |
| **Imports**       | Multiple paths        | Single clear path (+ shims)    |

## References

- [ADR-0004: Chiron Subsystem Extraction](ADRs/ADR-0004-chiron-subsystem-extraction.md)
- [Chiron README](chiron/README.md)
- [Chiron Quick Reference](chiron/QUICK_REFERENCE.md)
- [Module Boundaries](module-boundaries.md)
