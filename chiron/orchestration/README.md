# Chiron Orchestration Module

Unified orchestration and coordination for the Prometheus dependency management pipeline.

## Overview

The orchestration module provides high-level coordination across multiple subsystems:

- **Dependency Management** - Preflight, guard, upgrade, and sync
- **Packaging** - Wheelhouse building and offline packaging
- **Automated Synchronization** - Intelligent self-updating with error recovery
- **Environment Management** - Dev/prod environment synchronization
- **Validation** - Post-operation health checks

## Components

### OrchestrationCoordinator

Main coordination class for all pipeline operations.

```python
from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext

context = OrchestrationContext(
    dry_run=False,
    verbose=True,
)
coordinator = OrchestrationCoordinator(context)

# Run full dependency workflow
results = coordinator.full_dependency_workflow(
    auto_upgrade=True,
    force_sync=False,
)
```

### AutoSyncOrchestrator

Intelligent, self-updating dependency management with graceful error handling.

```python
from chiron.orchestration import AutoSyncOrchestrator, AutoSyncConfig

config = AutoSyncConfig(
    auto_upgrade=True,
    auto_apply_safe=True,
    enable_rollback=True,
    sync_dev_env=True,
    sync_prod_env=False,
)
orchestrator = AutoSyncOrchestrator(config)

# Execute automated sync
result = orchestrator.execute()

if result.success:
    print(f"✅ Sync completed: {len(result.updates_applied)} updates applied")
else:
    print(f"⚠️  Sync failed: {len(result.errors)} errors")
    if result.rollback_performed:
        print("🔄 Rollback completed")
```

## Workflows

### Full Dependency Workflow

Comprehensive dependency management pipeline:

1. Preflight checks
2. Upgrade guard assessment
3. Optional upgrade planning
4. Dependency synchronization

```python
results = coordinator.full_dependency_workflow(
    auto_upgrade=True,
    force_sync=False,
)
```

### Intelligent Upgrade Workflow

Smart upgrade with mirror synchronization:

1. Generate upgrade advice
2. Auto-apply safe upgrades
3. Update mirror
4. Validate environment

```python
results = coordinator.intelligent_upgrade_workflow(
    auto_apply_safe=True,
    update_mirror=True,
)
```

### Air-Gapped Preparation Workflow

Complete offline deployment preparation:

1. Full dependency workflow
2. Build wheelhouse (multi-platform)
3. Download models
4. Package containers
5. Generate checksums and manifests
6. Validate complete package

```python
results = coordinator.air_gapped_preparation_workflow(
    include_models=True,
    include_containers=False,
    validate=True,
)
```

### Automated Sync Workflow

Self-updating with error recovery:

1. Create snapshot for rollback
2. Assess available updates
3. Apply safe updates
4. Sync environments
5. Validate results
6. Rollback on failure

```python
orchestrator = AutoSyncOrchestrator(config)
result = orchestrator.execute()
```

## CLI Usage

### Orchestration Commands

```bash
# Show orchestration status
prometheus orchestrate status

# Full dependency workflow
prometheus orchestrate full-dependency \
  --auto-upgrade \
  --force-sync

# Full packaging workflow
prometheus orchestrate full-packaging \
  --validate

# Sync remote artifacts
prometheus orchestrate sync-remote /path/to/artifacts \
  --validate
```

### Auto-Sync Commands

```bash
# Execute automated sync
prometheus orchestrate auto-sync \
  --verbose

# Dry run (no changes)
prometheus orchestrate auto-sync \
  --dry-run \
  --verbose

# Production sync (requires opt-in)
prometheus orchestrate auto-sync \
  --sync-prod \
  --no-auto-apply \
  --verbose

# Check auto-sync status
prometheus orchestrate auto-sync-status --verbose
```

## Configuration

### Environment-Specific Configs

**Development:** `configs/defaults/auto_sync_dev.toml`
- Aggressive update policy
- Daily schedule
- Auto-apply safe updates

**Production:** `configs/defaults/auto_sync_prod.toml`
- Conservative update policy
- Weekly schedule
- Manual approval required

### Configuration Options

```python
config = AutoSyncConfig(
    # Sync behavior
    auto_upgrade=True,
    auto_apply_safe=True,
    force_sync=False,
    update_mirror=True,
    
    # Safety thresholds
    max_major_updates=0,  # Block major updates
    max_minor_updates=5,
    max_patch_updates=20,
    
    # Error handling
    enable_rollback=True,
    max_retry_attempts=3,
    continue_on_error=False,
    
    # Environment sync
    sync_dev_env=True,
    sync_prod_env=False,  # Requires explicit opt-in
    validate_after_sync=True,
    
    # Metadata
    dry_run=False,
    verbose=False,
)
```

## Safety Mechanisms

### 1. Snapshot and Rollback

Before any changes:
- Creates snapshot of current state
- Includes hashes of lock files, manifests, and contracts
- Automatically rolls back via git on failure

### 2. Guard Assessment

All updates evaluated by upgrade guard:
- `safe` - Updates pass all checks
- `needs-review` - Updates have warnings
- `blocked` - Updates fail safety checks (auto-stopped)

### 3. Update Thresholds

Configurable limits prevent runaway updates:
- Major updates: Default 0 (blocked)
- Minor updates: Configurable per environment
- Patch updates: Liberal by default

### 4. Environment Isolation

Separate policies for dev and prod:
- Development: More aggressive, auto-apply
- Production: Conservative, manual approval

## State Management

### State Files

```bash
# Orchestration state
var/orchestration-state.json

# Auto-sync state
var/auto-sync-state.json

# Snapshot for rollback
var/auto-sync-snapshot.json

# Guard assessments
var/upgrade-guard/assessment.json
var/upgrade-guard/runs/<run-id>/
```

### Status Inspection

```python
# Orchestration status
status = coordinator.get_status()
print(status["recommendations"])

# Auto-sync status
status = orchestrator.get_status()
print(status["last_run"])
```

## Integration with CI

### GitHub Actions

Automated sync workflow: `.github/workflows/automated-dependency-sync.yml`

**Features:**
- Scheduled execution
- Manual dispatch with options
- PR creation for updates
- Slack notifications
- Artifact archival

**Triggers:**
```yaml
on:
  schedule:
    - cron: "0 5 * * *"  # Daily at 5:00 UTC
  workflow_dispatch:
    inputs:
      dry-run: ...
      sync-prod: ...
```

## Testing

### Unit Tests

```bash
# Test auto-sync module
pytest tests/unit/chiron/test_auto_sync.py -v

# Test coordinator
pytest tests/unit/chiron/test_orchestration_coordinator.py -v
```

### Integration Tests

```bash
# Full workflow test (dry-run)
poetry run prometheus orchestrate auto-sync --dry-run --verbose

# Test with actual changes (development)
poetry run prometheus orchestrate auto-sync --verbose
```

## Monitoring and Alerts

### Health Checks

```bash
# Overall status
poetry run prometheus orchestrate status

# Auto-sync status
poetry run prometheus orchestrate auto-sync-status

# Guard assessment
poetry run prometheus deps guard --output /tmp/guard.json
```

### Logs and Artifacts

**Local:**
- `var/auto-sync/output.log`
- `var/auto-sync-state.json`

**CI:**
- GitHub Actions workflow logs
- Downloadable artifacts
- Auto-generated PRs

### Slack Notifications

Configure via `DEPENDENCY_GUARD_SLACK_WEBHOOK`:
- ✅ Success with updates
- ⚠️  Failures or errors
- 🚫 Blocked by guard

## Best Practices

### 1. Always Test First

```bash
# Dry run before applying changes
poetry run prometheus orchestrate auto-sync --dry-run --verbose
```

### 2. Review Guard Reports

```bash
# Check guard status before sync
poetry run prometheus deps guard

# Review flagged packages
cat var/upgrade-guard/summary.md
```

### 3. Use Environment-Specific Configs

```bash
# Development (aggressive)
poetry run prometheus orchestrate auto-sync

# Production (conservative)
poetry run prometheus orchestrate auto-sync --sync-prod --no-auto-apply
```

### 4. Monitor State Files

```bash
# Check last run
cat var/auto-sync-state.json | jq '.'

# Check snapshot
cat var/auto-sync-snapshot.json | jq '.'
```

## Troubleshooting

See [Automated Dependency Sync Runbook](../../docs/runbooks/automated-dependency-sync.md) for detailed troubleshooting procedures.

## Related Documentation

- [Dependency Governance Handbook](../../docs/dependency-governance.md)
- [Automated Dependency Sync Runbook](../../docs/runbooks/automated-dependency-sync.md)
- [Gap Analysis](../../docs/archive/dependency-upgrade-gap-analysis.md)

## API Reference

### Classes

- `OrchestrationContext` - Execution context
- `OrchestrationCoordinator` - Main coordinator
- `AutoSyncConfig` - Auto-sync configuration
- `AutoSyncOrchestrator` - Auto-sync coordinator
- `AutoSyncResult` - Sync result with metadata

### Key Methods

**OrchestrationCoordinator:**
- `full_dependency_workflow()` - Complete dependency pipeline
- `intelligent_upgrade_workflow()` - Smart upgrades with advice
- `air_gapped_preparation_workflow()` - Offline deployment prep
- `get_status()` - Current status and recommendations

**AutoSyncOrchestrator:**
- `execute()` - Run automated sync
- `get_status()` - Last run status
- `_assess_updates()` - Evaluate available updates
- `_rollback()` - Rollback to snapshot

---

For more information, see the [Prometheus documentation](../../README.md).
