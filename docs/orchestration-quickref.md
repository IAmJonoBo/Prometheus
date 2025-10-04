# Prometheus Orchestration Quick Reference

> Unified commands for seamless dependency management, packaging, and deployment

## Quick Start

```bash
# Check what needs to be done
prometheus orchestrate status

# Run full dependency workflow
prometheus orchestrate full-dependency --auto-upgrade --force-sync

# Run full packaging workflow
prometheus orchestrate full-packaging --validate

# Sync remote CI build to local
prometheus orchestrate sync-remote ./offline-packaging-suite-optimized
```

## Common Workflows

### Daily Development

```bash
# Morning: Check status
prometheus orchestrate status

# Work on features...

# Before commit: Validate dependencies
prometheus deps preflight --json
```

### Weekly Maintenance

```bash
# Monday: Full dependency check + packaging
prometheus orchestrate full-dependency --auto-upgrade
prometheus orchestrate full-packaging --validate

# Review recommendations
prometheus orchestrate status --verbose

# Check results
cat var/upgrade-guard/summary.md
cat var/remediation-recommendations.json | jq -r '.recommendations[]'
```

### Pre-Release

```bash
# 1. Ensure dependencies are current and safe
prometheus orchestrate full-dependency --force-sync

# 2. Build fresh offline packages
prometheus orchestrate full-packaging --validate

# 3. Check everything is ready
prometheus orchestrate status

# 4. If issues found, review and fix
[ -f var/remediation-recommendations.json ] && \
  cat var/remediation-recommendations.json | jq .
```

### CI Artifact Integration

```bash
# 1. Download latest CI build
gh run list --workflow=offline-packaging-optimized --limit 1
gh run download <run-id> -n offline-packaging-suite-optimized

# 2. Sync to local environment
prometheus orchestrate sync-remote ./offline-packaging-suite-optimized

# 3. Validate locally
prometheus orchestrate status
prometheus offline-doctor --format table
```

### Air-Gapped Deployment Prep

```bash
# 1. Build complete package
prometheus orchestrate full-packaging --validate

# 2. Verify all components
prometheus offline-doctor --package-dir vendor/offline --format json

# 3. Create deployment bundle
cd vendor/offline
tar -czf ../../prometheus-airgapped-$(date +%Y%m%d).tar.gz .
cd ../..
sha256sum prometheus-airgapped-*.tar.gz > prometheus-airgapped-*.tar.gz.sha256

# 4. Transfer to target environment
```

## Individual Commands

### Dependency Management

```bash
# Health check
prometheus deps preflight --json > /tmp/preflight.json

# Risk analysis
prometheus deps guard \
  --preflight /tmp/preflight.json \
  --output var/upgrade-guard/assessment.json

# Plan upgrades
prometheus deps upgrade \
  --sbom var/dependency-sync/sbom.json \
  --planner-limit 10

# Apply upgrades
prometheus deps upgrade \
  --sbom var/dependency-sync/sbom.json \
  --apply --yes

# Sync contracts
prometheus deps sync --apply --force

# Check status
prometheus deps status
```

### Packaging

```bash
# Build wheelhouse
bash scripts/build-wheelhouse.sh vendor/wheelhouse

# Full offline package
prometheus offline-package \
  --auto-update \
  --auto-update-max minor

# Validate package
prometheus offline-doctor \
  --package-dir vendor/offline \
  --format table
```

### Remediation

```bash
# Analyze wheelhouse failures
prometheus remediation wheelhouse \
  --input var/offline-doctor-results.json \
  --output var/remediation-recommendations.json

# View recommendations
cat var/remediation-recommendations.json | jq -r '.recommendations[] | "• " + .'
```

### Mirror Management

```bash
# Check mirror status
python scripts/mirror_manager.py --status --json

# Update mirror
python scripts/mirror_manager.py \
  --update \
  --source vendor/wheelhouse \
  --prune
```

## Troubleshooting

### Reset orchestration state

```bash
rm var/orchestration-state.json
prometheus orchestrate status  # Rebuilds state
```

### Force dependency sync

```bash
prometheus deps sync --apply --force
```

### View detailed logs

```bash
prometheus orchestrate full-dependency --verbose
prometheus orchestrate full-packaging --verbose
```

### Check individual subsystem status

```bash
# Dependencies
prometheus deps status

# Packaging
prometheus offline-doctor --format table

# Mirror
python scripts/mirror_manager.py --status

# Temporal (if configured)
prometheus temporal test-connection
```

## File Locations

### State and Metadata

```
var/orchestration-state.json              # Orchestration state
var/dependency-preflight/latest.json      # Preflight results
var/upgrade-guard/assessment.json         # Guard analysis
var/upgrade-guard/summary.md              # Human-readable summary
var/upgrade-guard/runs/                   # Historical snapshots
var/offline-doctor-results.json           # Validation results
var/remediation-recommendations.json      # Fix suggestions
```

### Artifacts

```
vendor/wheelhouse/                        # Offline installation wheels
vendor/offline/                           # Complete air-gapped bundle
vendor/models/                            # Cached ML models
vendor/images/                            # Container exports
dist/wheelhouse/                          # Build-time wheelhouse
```

### Configuration

```
configs/dependency-profile.toml           # Dependency policy
configs/defaults/pipeline.toml            # Pipeline config
configs/defaults/offline_package.toml     # Packaging config
constraints/production.txt                # Production constraints
```

## Environment Variables

```bash
# Temporal configuration (optional)
export TEMPORAL_SNAPSHOT_HOST="temporal.example.com:7233"
export TEMPORAL_SNAPSHOT_NAMESPACE="default"
export TEMPORAL_SNAPSHOT_TASK_QUEUE="prometheus-pipeline"

# Slack notifications (optional)
export DEPENDENCY_GUARD_SLACK_WEBHOOK="https://hooks.slack.com/..."

# Metrics (optional)
export PROMETHEUS_METRICS_HOST="prometheus.example.com"
export PROMETHEUS_METRICS_PORT="9090"
```

## Exit Codes

- `0` - Success
- `1` - Failure (validation failed, command error, etc.)
- `2` - Configuration error

## Performance Tips

1. **Use --dry-run** for testing workflows without side effects
2. **Use --verbose** for debugging issues
3. **Cache wheelhouse** between runs (already handled by coordinator)
4. **Run full workflows** weekly, individual commands as needed
5. **Check status** before major operations

## Integration with CI/CD

```yaml
# GitHub Actions example
- name: Full orchestration workflow
  run: |
    poetry run prometheus orchestrate full-dependency --force-sync
    poetry run prometheus orchestrate full-packaging --validate
    poetry run prometheus orchestrate status

# Check exit code
- name: Verify orchestration status
  run: |
    poetry run prometheus orchestrate status --verbose
```

## Python API

```python
from scripts.orchestration_coordinator import (
    OrchestrationCoordinator,
    OrchestrationContext,
)

# Create coordinator
context = OrchestrationContext(verbose=True)
coordinator = OrchestrationCoordinator(context)

# Run workflows
coordinator.full_dependency_workflow(auto_upgrade=True, force_sync=True)
coordinator.full_packaging_workflow(validate=True)

# Check status
status = coordinator.get_status()
for rec in status["recommendations"]:
    print(f"→ {rec}")
```

## Documentation

- [orchestration-enhancement.md](./orchestration-enhancement.md) - Complete guide
- [workflow-orchestration.md](./workflow-orchestration.md) - Workflow architecture
- [cibuildwheel-integration.md](./cibuildwheel-integration.md) - Multi-platform builds
- [cross-workflow-integration.md](./cross-workflow-integration.md) - Integration patterns
- [dependency-management-pipeline.md](./dependency-management-pipeline.md) - Dependency subsystem

## Support

For issues:

1. Check `prometheus orchestrate status --verbose`
2. Review `var/orchestration-state.json`
3. Check logs in `var/` directories
4. Review [orchestration-enhancement.md](./orchestration-enhancement.md) troubleshooting section
