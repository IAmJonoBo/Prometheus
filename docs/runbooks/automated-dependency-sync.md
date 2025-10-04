# Automated Dependency Synchronization Runbook

> **Version:** 1.0  
> **Updated:** 2025-01-04  
> **Audience:** Platform operators, SREs, DevOps engineers

## Overview

The automated dependency synchronization system provides intelligent,
self-updating dependency management for the Prometheus pipeline. It uses the
Prometheus system itself to manage updates, with graceful error handling,
rollback capabilities, and environment-specific policies.

## System Components

### Core Components

- **Auto-Sync Orchestrator** (`chiron/orchestration/auto_sync.py`)
  - Main coordination logic
  - Snapshot creation for rollback
  - Update assessment and application
  - Environment synchronization
  - Validation and error handling

- **CLI Interface** (`prometheus orchestrate auto-sync`)
  - Manual execution
  - Status inspection
  - Configuration override

- **GitHub Actions Workflow** (`.github/workflows/automated-dependency-sync.yml`)
  - Scheduled execution
  - PR creation for updates
  - Slack notifications
  - Artifact archival

### Supporting Components

- **Dependency Guard** (`chiron/deps/guard.py`) - Safety assessment
- **Upgrade Planner** (`chiron/deps/planner.py`) - Update planning
- **Dependency Sync** (`chiron/deps/sync.py`) - Manifest synchronization
- **Orchestration Coordinator** (`chiron/orchestration/coordinator.py`) - Workflow coordination

## Configuration

### Environment-Specific Configs

**Development:** `configs/defaults/auto_sync_dev.toml`
- More aggressive update policy
- Daily schedule
- Auto-apply safe updates

**Production:** `configs/defaults/auto_sync_prod.toml`
- Conservative update policy
- Weekly schedule
- Manual approval for most updates
- Auto-approve patches only

### Environment Variables

```bash
# Temporal credentials (optional)
TEMPORAL_SNAPSHOT_HOST=temporal.example.com:7233
TEMPORAL_SNAPSHOT_NAMESPACE=prometheus
TEMPORAL_SNAPSHOT_TASK_QUEUE=prometheus-pipeline

# Slack notifications (optional)
DEPENDENCY_GUARD_SLACK_WEBHOOK=https://hooks.slack.com/services/...

# Git credentials (for CI)
GITHUB_TOKEN=ghp_...
```

## Operational Procedures

### Manual Execution

#### 1. Dry Run (Recommended First)

```bash
# Preview what would happen without making changes
poetry run prometheus orchestrate auto-sync --dry-run --verbose
```

#### 2. Development Environment

```bash
# Execute with default dev settings
poetry run prometheus orchestrate auto-sync --verbose

# Execute with custom options
poetry run prometheus orchestrate auto-sync \
  --verbose \
  --no-auto-apply  # Plan but don't apply updates
```

#### 3. Production Environment

```bash
# Production sync (requires explicit opt-in)
poetry run prometheus orchestrate auto-sync \
  --sync-prod \
  --no-auto-apply \
  --verbose

# Review the plan, then apply manually if approved
```

### Status Inspection

```bash
# Check last run status
poetry run prometheus orchestrate auto-sync-status

# Verbose status with full details
poetry run prometheus orchestrate auto-sync-status --verbose
```

## Safety Mechanisms

### 1. Snapshot and Rollback

**How it works:**
- Before any changes, a snapshot of current state is created
- Includes hashes of `poetry.lock`, `pyproject.toml`, and contract files
- On failure, automatically rolls back via `git checkout`

**Manual rollback:**
```bash
# If automatic rollback fails
git checkout HEAD poetry.lock pyproject.toml
git status
```

### 2. Guard Assessment

**Statuses:**
- `safe` - Updates pass all checks, can proceed
- `needs-review` - Updates have warnings, manual review recommended
- `blocked` - Updates fail safety checks, automatically stopped

### 3. Update Thresholds

**Default limits (development):**
- Major updates: 0 (blocked)
- Minor updates: 10 per run
- Patch updates: 50 per run

**Default limits (production):**
- Major updates: 0 (blocked)
- Minor updates: 3 per run
- Patch updates: 20 per run

## Troubleshooting

### Issue: Auto-sync fails with "blocked by guard"

**Cause:** Dependencies have security vulnerabilities or policy violations

**Resolution:**
1. Check guard report: `var/upgrade-guard/summary.md`
2. Review flagged packages
3. Options:
   - Wait for upstream fixes
   - Update contract to snooze temporarily
   - Manual investigation and patching

### Issue: Rollback fails

**Cause:** Git state inconsistent or files modified outside git

**Resolution:**
1. Manual rollback:
   ```bash
   git checkout HEAD poetry.lock pyproject.toml
   git reset --hard HEAD
   ```

2. Verify state:
   ```bash
   git status
   poetry check
   ```

## Best Practices

### 1. Regular Review

- Weekly: Review guard reports and update trends
- Monthly: Audit contract policies and thresholds
- Quarterly: Review and update operational runbooks

### 2. Testing Changes

- Always dry-run first in production
- Test updates in development before production
- Validate with full test suite after updates

### 3. Security

- Rotate webhook URLs periodically
- Audit approved packages quarterly
- Monitor CVE feeds for critical issues

## Reference

### Related Documentation

- [Dependency Governance Handbook](../dependency-governance.md)
- [Gap Analysis](../archive/dependency-upgrade-gap-analysis.md)

### CLI Reference

```bash
# Auto-sync commands
prometheus orchestrate auto-sync --help
prometheus orchestrate auto-sync-status --help

# Dependency commands
prometheus deps guard --help
prometheus deps upgrade --help
prometheus deps sync --help
prometheus deps status --help
```

---

**Document History:**
- 2025-01-04: Initial version
- Future updates: Track in git history
