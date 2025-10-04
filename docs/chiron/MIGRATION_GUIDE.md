# Chiron Migration Guide

## Overview

This guide helps you transition from the old scattered tooling structure to the new unified Chiron subsystem.

## What Changed?

### Structural Changes

| Old Location                           | New Location                          | Status          |
| -------------------------------------- | ------------------------------------- | --------------- |
| `prometheus/packaging/`                | `chiron/packaging/`                   | Moved with shim |
| `prometheus/remediation/`              | `chiron/remediation/`                 | Moved with shim |
| `scripts/orchestration_coordinator.py` | `chiron/orchestration/coordinator.py` | Moved with shim |
| `scripts/deps_status.py`               | `chiron/deps/status.py`               | Moved with shim |
| `scripts/upgrade_guard.py`             | `chiron/deps/guard.py`                | Moved           |
| `scripts/upgrade_planner.py`           | `chiron/deps/planner.py`              | Moved           |
| `scripts/dependency_drift.py`          | `chiron/deps/drift.py`                | Moved           |
| `scripts/sync-dependencies.py`         | `chiron/deps/sync.py`                 | Moved           |
| `scripts/preflight_deps.py`            | `chiron/deps/preflight.py`            | Moved           |
| `scripts/offline_doctor.py`            | `chiron/doctor/offline.py`            | Moved           |
| `scripts/offline_package.py`           | `chiron/doctor/package_cli.py`        | Moved           |

### CLI Changes

| Old Command                         | New Command                             | Notes                    |
| ----------------------------------- | --------------------------------------- | ------------------------ |
| `prometheus offline-package`        | `python -m chiron package offline`      | Old works via delegation |
| `prometheus offline-doctor`         | `python -m chiron doctor offline`       | Old works via delegation |
| `prometheus deps status`            | `python -m chiron deps status`          | Old works via delegation |
| `prometheus deps guard`             | `python -m chiron deps guard`           | Old works via delegation |
| `prometheus deps upgrade`           | `python -m chiron deps upgrade`         | Old works via delegation |
| `prometheus orchestrate status`     | `python -m chiron orchestrate status`   | Old works via delegation |
| `prometheus remediation wheelhouse` | `python -m chiron remediate wheelhouse` | Old works via delegation |

**Important**: All old commands still work! They delegate to Chiron internally.

## Migration Strategies

### Strategy 1: No Changes Required (Recommended for Most Users)

**If you only use CLI commands**, no changes are needed. All commands work as before:

```bash
# Continue using these - they work fine
prometheus offline-package
prometheus deps status
prometheus orchestrate full-dependency
```

### Strategy 2: Gradual Migration (Recommended for Library Users)

**If you import from old paths**, your code still works via shims:

```python
# Old imports - still work via shims
from prometheus.packaging import OfflinePackagingOrchestrator
from prometheus.remediation import WheelhouseRemediator
from scripts.orchestration_coordinator import OrchestrationCoordinator

# ✅ No changes needed - shims handle redirection
```

**For new code**, use the new paths:

```python
# New imports - recommended for new code
from chiron.packaging import OfflinePackagingOrchestrator
from chiron.remediation import WheelhouseRemediator
from chiron.orchestration import OrchestrationCoordinator
```

### Strategy 3: Full Migration (Optional)

**If you want to fully adopt the new structure**, update imports in your codebase:

#### Before

```python
# Old imports
from prometheus.packaging import (
    OfflinePackagingOrchestrator,
    OfflinePackagingConfig,
)
from prometheus.remediation import WheelhouseRemediator
from scripts.orchestration_coordinator import (
    OrchestrationCoordinator,
    OrchestrationContext,
)
from scripts.deps_status import generate_status, DependencyStatus
from scripts.upgrade_guard import main as guard_main
from scripts.upgrade_planner import main as planner_main
```

#### After

```python
# New imports
from chiron.packaging import (
    OfflinePackagingOrchestrator,
    OfflinePackagingConfig,
)
from chiron.remediation import WheelhouseRemediator
from chiron.orchestration import (
    OrchestrationCoordinator,
    OrchestrationContext,
)
from chiron.deps.status import generate_status, DependencyStatus
from chiron.deps.guard import main as guard_main
from chiron.deps.planner import main as planner_main
```

## Common Migration Scenarios

### Scenario 1: CI/CD Scripts

**Before:**

```bash
#!/bin/bash
# Old CI script
prometheus offline-package --verbose
prometheus deps guard --fail-threshold needs-review
```

**After (Option 1 - No Changes):**

```bash
#!/bin/bash
# Still works - no changes needed
prometheus offline-package --verbose
prometheus deps guard --fail-threshold needs-review
```

**After (Option 2 - Use Chiron Directly):**

```bash
#!/bin/bash
# Use Chiron directly
python -m chiron package offline --verbose
python -m chiron deps guard --fail-threshold needs-review
```

### Scenario 2: Python Scripts

**Before:**

```python
# Old Python script
from prometheus.packaging import OfflinePackagingOrchestrator

def build_package():
    orchestrator = OfflinePackagingOrchestrator()
    result = orchestrator.execute()
    return result
```

**After (Option 1 - No Changes):**

```python
# Still works via shim - no changes needed
from prometheus.packaging import OfflinePackagingOrchestrator

def build_package():
    orchestrator = OfflinePackagingOrchestrator()
    result = orchestrator.execute()
    return result
```

**After (Option 2 - Update Import):**

```python
# Updated to use Chiron directly
from chiron.packaging import OfflinePackagingOrchestrator

def build_package():
    orchestrator = OfflinePackagingOrchestrator()
    result = orchestrator.execute()
    return result
```

### Scenario 3: Tests

**Before:**

```python
# Old test
from prometheus.packaging import OfflinePackagingOrchestrator

def test_packaging():
    orchestrator = OfflinePackagingOrchestrator()
    assert orchestrator is not None
```

**After (Recommended):**

```python
# Updated test - use new path
from chiron.packaging import OfflinePackagingOrchestrator

def test_packaging():
    orchestrator = OfflinePackagingOrchestrator()
    assert orchestrator is not None
```

## Finding What You Need

### Quick Lookup Table

| What You Want     | Where to Find It                                         |
| ----------------- | -------------------------------------------------------- |
| Offline packaging | `chiron.packaging` or `python -m chiron package`         |
| Dependency status | `chiron.deps.status` or `python -m chiron deps status`   |
| Upgrade planning  | `chiron.deps.planner` or `python -m chiron deps upgrade` |
| Guard checks      | `chiron.deps.guard` or `python -m chiron deps guard`     |
| Drift detection   | `chiron.deps.drift` or `python -m chiron deps drift`     |
| Remediation       | `chiron.remediation` or `python -m chiron remediate`     |
| Orchestration     | `chiron.orchestration` or `python -m chiron orchestrate` |
| Diagnostics       | `chiron.doctor` or `python -m chiron doctor`             |

### Discovery Commands

```bash
# Show all Chiron commands
python -m chiron --help

# Show dependency commands
python -m chiron deps --help

# Show packaging commands
python -m chiron package --help

# Show orchestration commands
python -m chiron orchestrate --help
```

## Testing Your Migration

### Step 1: Verify Old Paths Still Work

```bash
# Should work without errors
prometheus offline-doctor
prometheus deps status
```

### Step 2: Try New Chiron CLI

```bash
# Should produce identical output
python -m chiron doctor offline
python -m chiron deps status
```

### Step 3: Test Updated Imports

```python
# Create test file: test_chiron_migration.py
from chiron.packaging import OfflinePackagingOrchestrator
from chiron.deps.status import generate_status

def test_imports():
    """Verify new imports work."""
    assert OfflinePackagingOrchestrator is not None
    assert generate_status is not None
    print("✅ New imports work correctly")

if __name__ == "__main__":
    test_imports()
```

```bash
# Run test
python test_chiron_migration.py
```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'chiron'`

**Solution**: Make sure you're in the repository root and the `chiron/` directory exists:

```bash
cd /path/to/Prometheus
ls -la chiron/
```

### CLI Not Found

**Problem**: `python -m chiron` doesn't work

**Solution**: Use the full path or add to PYTHONPATH:

```bash
# Option 1: Run from repo root
cd /path/to/Prometheus
python -m chiron --help

# Option 2: Add to PYTHONPATH
export PYTHONPATH="/path/to/Prometheus:$PYTHONPATH"
python -m chiron --help
```

### Old Imports Not Working

**Problem**: Old imports fail even with shims

**Solution**: Check that compatibility shims exist:

```bash
ls -la prometheus/packaging/__init__.py
ls -la prometheus/remediation.py
ls -la scripts/_compat_*.py
```

If missing, these need to be restored from the migration commit.

## FAQ

### Q: Do I need to change my code immediately?

**A**: No. All old paths work via compatibility shims. Change at your convenience.

### Q: When will old paths be removed?

**A**: Not until a major version bump (e.g., 2.0.0). You'll have plenty of warning.

### Q: Can I mix old and new imports?

**A**: Yes, they point to the same code. However, for consistency, stick to one style per file.

### Q: What about my CI/CD pipelines?

**A**: They should work without changes. Old commands delegate to Chiron automatically.

### Q: Should I use `prometheus` or `python -m chiron`?

**A**: For tooling commands, `python -m chiron` is more explicit and recommended. For pipeline commands, use `prometheus`.

### Q: Where can I learn more?

**A**: See the comprehensive documentation:

- [Chiron README](README.md)
- [Quick Reference](QUICK_REFERENCE.md)
- [Architecture Guide](ARCHITECTURE.md)
- [ADR-0004](../ADRs/ADR-0004-chiron-subsystem-extraction.md)

## Getting Help

If you encounter issues:

1. **Check status**: `python -m chiron orchestrate status`
2. **Run diagnostics**: `python -m chiron doctor offline`
3. **Review docs**: `docs/chiron/`
4. **Check logs**: `var/` directory
5. **Open an issue**: Include error messages and context

## Summary

- ✅ **No immediate action required** - Old paths still work
- ✅ **Gradual migration recommended** - Update new code to use Chiron paths
- ✅ **Full backwards compatibility** - All old commands and imports work
- ✅ **Enhanced discoverability** - `python -m chiron` provides unified access
- ✅ **Better architecture** - Clear separation of concerns

The migration is designed to be **zero-friction**. Take your time and migrate at your own pace!
