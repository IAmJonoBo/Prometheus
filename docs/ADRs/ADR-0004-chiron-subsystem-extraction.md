# ADR-0004: Chiron Subsystem Extraction

## Status

**Accepted** — October 2024

## Context

The Prometheus codebase originally mixed runtime pipeline concerns (ingestion → retrieval → reasoning → decision → execution → monitoring) with build-time tooling concerns (packaging, dependency management, diagnostics, remediation). This created several problems:

1. **Unclear Boundaries**: Pipeline stages and developer tooling were not clearly separated
2. **Mixed Concerns**: Runtime event-driven code was intermingled with command-line tools
3. **Difficult Testing**: Testing pipeline logic required understanding packaging logic and vice versa
4. **Poor Discoverability**: Developers had to search through `scripts/` and `prometheus/` to find tooling
5. **Maintenance Burden**: Changes to packaging affected pipeline code and vice versa
6. **Evolution Friction**: Packaging tools couldn't evolve independently from pipeline semantics

The original structure:
- `prometheus/packaging/` — Offline packaging
- `prometheus/remediation/` — Failure remediation
- `scripts/` — Scattered tooling scripts (orchestration, deps, guard, planner, drift, etc.)
- `prometheus/cli.py` — Monolithic CLI mixing pipeline and tooling commands

## Decision

We extract all packaging, dependency management, and developer tooling into a separate **Chiron subsystem** with clear module boundaries:

### New Structure

```
chiron/                          # New top-level subsystem
├── packaging/                   # From prometheus/packaging/
│   ├── offline.py
│   └── metadata.py
├── remediation/                 # From prometheus/remediation/
│   ├── __init__.py
│   ├── runtime.py
│   └── github_summary.py
├── deps/                        # From scripts/
│   ├── status.py               # From scripts/deps_status.py
│   ├── guard.py                # From scripts/upgrade_guard.py
│   ├── planner.py              # From scripts/upgrade_planner.py
│   ├── drift.py                # From scripts/dependency_drift.py
│   ├── sync.py                 # From scripts/sync-dependencies.py
│   ├── preflight.py            # From scripts/preflight_deps.py
│   └── mirror_manager.py       # From scripts/mirror_manager.py
├── orchestration/               # From scripts/
│   └── coordinator.py          # From scripts/orchestration_coordinator.py
├── doctor/                      # From scripts/
│   ├── offline.py              # From scripts/offline_doctor.py
│   └── package_cli.py          # From scripts/offline_package.py
├── cli.py                       # New unified CLI
└── __main__.py                  # CLI entry point
```

### Principles

1. **Separation of Concerns**:
   - **Prometheus**: Runtime strategy decisions (event-driven pipeline)
   - **Chiron**: Build-time tooling (command-driven utilities)

2. **Independent Evolution**:
   - Chiron can evolve without affecting pipeline semantics
   - Pipeline can evolve without affecting packaging tools
   - Clear ownership boundaries

3. **Backwards Compatibility**:
   - Old import paths maintained via shims:
     - `prometheus.packaging` → `chiron.packaging`
     - `prometheus.remediation` → `chiron.remediation`
     - `scripts.orchestration_coordinator` → `chiron.orchestration`
   - Old CLI commands still work:
     - `prometheus offline-package` → delegates to `chiron`
     - `prometheus deps status` → delegates to `chiron`

4. **Discoverability**:
   - All tooling accessible via `python -m chiron`
   - Comprehensive documentation in `docs/chiron/`
   - Unified CLI with clear command groups

### Module Boundaries

**Allowed**:
- `chiron/*` → other `chiron/*` modules ✅
- `chiron/*` → `observability/`, `prometheus/config` ✅ (shared infrastructure)
- `prometheus/cli.py` → `chiron/*` ✅ (for tooling commands only)

**Forbidden**:
- Pipeline stages → `chiron/*` ❌ (stages must not depend on build tooling)
- `chiron/*` → pipeline stages ❌ (tooling must remain independent)

### CLI Integration

Two entry points, same functionality:

```bash
# New direct access
python -m chiron deps status
python -m chiron package offline
python -m chiron orchestrate full-dependency

# Backwards compatible (delegates to chiron)
prometheus deps status
prometheus offline-package
prometheus orchestrate full-dependency
```

## Consequences

### Positive

1. **Clear Boundaries**: Pipeline and tooling are architecturally separate
2. **Better Testing**: Can test each subsystem independently
3. **Easier Onboarding**: Developers can focus on one subsystem at a time
4. **Independent Evolution**: Chiron and Prometheus can evolve separately
5. **Better Documentation**: Focused documentation for each subsystem
6. **Clearer Ownership**: Teams can own entire subsystems
7. **Reduced Coupling**: Changes in one subsystem don't ripple to the other

### Negative

1. **Migration Effort**: Need to update imports across codebase
2. **Temporary Duplication**: Shims create some code duplication during transition
3. **Learning Curve**: Developers must learn new import paths
4. **CI/CD Updates**: May need to update some CI/CD workflows

### Mitigation

1. **Compatibility Shims**: All old paths still work
2. **Comprehensive Documentation**: `docs/chiron/` provides full guidance
3. **Gradual Migration**: Old code can use old paths; new code uses new paths
4. **Quick Reference**: `docs/chiron/QUICK_REFERENCE.md` for fast lookup

## Implementation

### Phase 1: Structure (Completed)
- ✅ Create `chiron/` directory structure
- ✅ Copy files from `prometheus/` and `scripts/`
- ✅ Fix internal imports within Chiron
- ✅ Create compatibility shims
- ✅ Update `prometheus/cli.py` to delegate to Chiron
- ✅ Create Chiron CLI (`chiron/cli.py`)

### Phase 2: Documentation (Completed)
- ✅ Create `docs/chiron/README.md`
- ✅ Create `docs/chiron/QUICK_REFERENCE.md`
- ✅ Update `docs/module-boundaries.md`
- ✅ Update `docs/README.md` and `docs/MODULE_INDEX.md`

### Phase 3: Migration (In Progress)
- ⏳ Update imports in tests
- ⏳ Update CI/CD workflows if needed
- ⏳ Add pyproject.toml entry point for `chiron`
- ⏳ Validate all commands work correctly

### Phase 4: Cleanup (Future)
- ⏳ Gradually migrate old imports to new paths
- ⏳ Add deprecation warnings to shims
- ⏳ Eventually remove old paths (major version bump)

## References

- [Chiron README](../chiron/README.md)
- [Chiron Quick Reference](../chiron/QUICK_REFERENCE.md)
- [Module Boundaries](../module-boundaries.md)
- [ADR-0001: Initial Architecture](ADR-0001-initial-architecture.md)
- [ADR-0002: Type Checking Dependency Management](ADR-0002-type-checking-dependency-management.md)

## Related Decisions

- **ADR-0001**: Established the initial event-driven architecture
- **ADR-0002**: Addressed dependency management complexity (now owned by Chiron)
- **ADR-0003**: Dry-run pipeline (remains in Prometheus, uses Chiron for artifacts)

## Future Considerations

1. **Plugin System**: Chiron could support third-party extensions
2. **Web UI**: Dashboard for dependency health and packaging status
3. **Auto-Remediation**: Automatic PR creation for dependency updates
4. **Multi-Repo**: Manage dependencies across multiple repositories
5. **Telemetry**: Enhanced observability for Chiron operations
