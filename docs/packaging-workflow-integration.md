# Packaging and Dependency Management Workflow Integration

This document describes how the packaging, dependency management, remediation,
and CLI commands work together to maintain a healthy offline-capable deployment
pipeline.

## Overview

The Prometheus CLI provides an integrated set of commands for:

- **Offline packaging**: Prepare wheelhouse, models, and containers
- **Dependency management**: Check status, plan upgrades, guard policies
- **Diagnostics**: Verify readiness and audit health
- **Remediation**: Auto-apply updates and repair issues

All commands are accessible via `prometheus <command>` and follow consistent
patterns for argument passing and exit codes.

## Command Groups

### Offline Packaging Commands

#### `prometheus offline-doctor`

Diagnose offline packaging readiness **without mutating** the repository.

**Purpose**: Pre-flight check before running packaging
**When to use**: Before `offline-package`, in CI health checks, troubleshooting

```bash
# Interactive table view
prometheus offline-doctor --format table

# JSON for automation/CI
prometheus offline-doctor --format json

# Traditional text output
prometheus offline-doctor
```

**What it checks**:

- Tool availability (Python, pip, Poetry, Docker)
- Git repository status and LFS
- Disk space
- Wheelhouse health
- Configuration validity

**Exit codes**:

- 0: All checks passed
- Non-zero: Issues detected (check output for details)

#### `prometheus offline-package`

Execute the full offline packaging workflow.

**Purpose**: Build complete offline deployment artifacts
**When to use**: Weekly refreshes, after dependency updates, before releases

```bash
# Full run with all phases
prometheus offline-package

# Specific phases only
prometheus offline-package --only-phase dependencies --only-phase checksums

# Skip specific phases
prometheus offline-package --skip-phase containers

# Dry run mode
prometheus offline-package --dry-run

# Enable auto-update for this run
prometheus offline-package --auto-update --auto-update-max minor

# Specify custom config
prometheus offline-package --config configs/custom/offline_package.toml
```

**Phases**:

1. `cleanup`: Remove stale artifacts
2. `environment`: Verify tooling and Python version
3. `dependencies`: Update wheelhouse, check for outdated packages
4. `models`: Download/update ML models
5. `containers`: Export Docker images
6. `checksums`: Generate SHA256 manifests
7. `git`: Verify LFS, normalize symlinks, ensure hooks

**Auto-update behavior**:

- Configured via `[updates.auto]` in config or CLI flags
- Can apply patch/minor/major updates automatically
- Logs auto-applied packages for review
- Generates audit trail in manifests

### Dependency Management Commands

#### `prometheus deps status`

Generate aggregated dependency status report.

**Purpose**: Unified view of dependency health
**When to use**: After packaging, before planning upgrades, in PR checks

```bash
# Interactive status display
prometheus deps status

# JSON output with file persistence
prometheus deps status --json --output var/deps-status.json

# Include guard markdown summary
prometheus deps status --markdown-output var/guard-summary.md --show-markdown

# Disable planner
prometheus deps status --no-planner

# Planner with specific packages
prometheus deps status --planner-package foo --planner-package bar
```

**Integrations**:

- Runs upgrade guard against contract
- Optionally runs upgrade planner
- Accepts SBOM, CVE data, Renovate configs
- Produces unified JSON and markdown reports

#### `prometheus deps upgrade`

Generate and optionally apply dependency upgrade plan.

**Purpose**: Propose and execute package updates
**When to use**: After reviewing status, for targeted updates

```bash
# Plan upgrades (no changes)
prometheus deps upgrade --sbom var/sbom.json

# Plan with specific packages
prometheus deps upgrade --sbom var/sbom.json \
  --planner-package requests --planner-package pydantic

# Apply upgrades interactively
prometheus deps upgrade --sbom var/sbom.json --apply

# Apply without confirmation
prometheus deps upgrade --sbom var/sbom.json --apply --yes

# Allow major version upgrades
prometheus deps upgrade --sbom var/sbom.json --planner-allow-major
```

**Workflow**:

1. Analyzes SBOM for outdated packages
2. Proposes Poetry update commands
3. Optionally validates with Poetry resolver
4. Applies updates when `--apply` is set
5. Logs all actions for audit

#### `prometheus deps guard`

Validate dependency changes against contract policies.

**Purpose**: Catch breaking changes and policy violations
**When to use**: In CI, before merging dependency PRs

```bash
# Check against default contract
prometheus deps guard

# Custom contract and SBOM
prometheus deps guard --contract policies/deps-contract.toml \
  --sbom var/sbom.json

# Set failure threshold
prometheus deps guard --fail-threshold blocked
```

#### `prometheus deps drift`

Compute dependency drift over time.

**Purpose**: Track upgrade momentum and lagging packages
**When to use**: Monthly reviews, roadmap planning

```bash
# Analyze drift from stored manifests
prometheus deps drift --sbom var/sbom.json
```

#### `prometheus deps sync`

Synchronize manifests from contract file.

**Purpose**: Enforce contract policy across environments
**When to use**: After contract updates, before air-gapped packaging

```bash
# Sync to contract
prometheus deps sync --apply

# Preview changes
prometheus deps sync
```

## Recommended Workflows

### 1. Pre-Packaging Health Check

Before running a major packaging operation:

```bash
# Step 1: Diagnose environment
prometheus offline-doctor --format table

# If issues found, resolve them, then re-check
prometheus offline-doctor --format table

# Step 2: Run packaging
prometheus offline-package

# Step 3: Review results
cat vendor/packaging-run.json | jq '.summary'
```

### 2. Dependency Update Cycle

When addressing dependency updates:

```bash
# Step 1: Check current status
prometheus deps status --json --output var/current-status.json

# Step 2: Plan upgrades (review output)
prometheus deps upgrade --sbom vendor/sbom.json --verbose

# Step 3: Apply upgrades for specific packages
prometheus deps upgrade --sbom vendor/sbom.json \
  --planner-package requests \
  --planner-package pydantic \
  --apply --yes

# Step 4: Validate with guard
prometheus deps guard --sbom vendor/sbom.json

# Step 5: Refresh wheelhouse
prometheus offline-package --only-phase dependencies

# Step 6: Verify health
prometheus offline-doctor --format json
```

### 3. CI Integration Pattern

Typical CI workflow combining commands:

```bash
#!/bin/bash
set -e

# Health check
if ! prometheus offline-doctor --format json > doctor-report.json; then
  echo "Doctor checks failed"
  exit 1
fi

# Run packaging
prometheus offline-package --verbose

# Check dependency status
prometheus deps status \
  --json \
  --output deps-status.json \
  --markdown-output guard-summary.md

# Validate contract
prometheus deps guard --fail-threshold needs-review

echo "All checks passed"
```

### 4. Auto-Remediation Flow

Using auto-update policies:

```bash
# Enable auto-update for this run only
prometheus offline-package \
  --auto-update \
  --auto-update-max patch \
  --auto-update-allow requests \
  --verbose

# Review what was auto-applied
cat vendor/packaging-run.json | jq '.updates.summary.auto_applied'

# Run smoke tests on auto-applied packages
poetry run pytest tests/smoke/

# If tests pass, commit changes
git add poetry.lock vendor/
git commit -m "chore: auto-applied patch updates"
```

### 5. Troubleshooting Packaging Failures

When packaging fails:

```bash
# Step 1: Run doctor to identify root cause
prometheus offline-doctor --format table --verbose

# Step 2: Check specific phase
prometheus offline-package \
  --only-phase dependencies \
  --verbose \
  --dry-run

# Step 3: Review dependency status
prometheus deps status --show-markdown

# Step 4: Check drift
prometheus deps drift --sbom vendor/sbom.json

# Step 5: After fixes, re-run
prometheus offline-doctor && prometheus offline-package
```

## Configuration Integration

All commands respect configuration files:

- **Offline packaging**: `configs/defaults/offline_package.toml`
- **Dependency contract**: `configs/deps-contract.toml` (default)
- **Pipeline**: `configs/defaults/pipeline.toml`

Override with `--config` flag or environment variables.

## Exit Code Conventions

All commands follow consistent exit code patterns:

- **0**: Success
- **1**: General failure or validation errors
- **2**: Configuration/file errors
- **3+**: Command-specific errors

Use `$?` to check exit codes in scripts:

```bash
if prometheus offline-doctor; then
  prometheus offline-package
else
  echo "Doctor checks failed, skipping packaging"
  exit 1
fi
```

## Observability and Telemetry

Commands emit:

- **Logs**: Structured logging to stderr
- **Metrics**: OpenTelemetry when enabled
- **Traces**: Spans for deps commands
- **Artifacts**: JSON manifests, markdown summaries

Use `--verbose` flags for detailed output.

## Best Practices

1. **Always run doctor first**: Catch environment issues early
2. **Use status before upgrade**: Understand current state
3. **Review auto-applied updates**: Don't blindly trust automation
4. **Keep contracts updated**: Reflect team policies
5. **Automate in CI**: Run health checks on every PR
6. **Version artifacts**: Tag packaging runs with git SHAs
7. **Monitor drift**: Address lagging packages monthly
8. **Document exceptions**: Note why packages are pinned

## Further Reading

- `docs/offline-packaging-status.md`: Current dependency state
- `docs/offline-doctor-enhancements.md`: Doctor capabilities
- `docs/dependency-governance.md`: Upgrade system design
- `docs/upgrade-guard.md`: Contract policy details
- `prometheus --help`: Full CLI reference
- `prometheus deps --help`: Dependency commands
- `prometheus offline-doctor --help`: Doctor options
- `prometheus offline-package --help`: Packaging options
