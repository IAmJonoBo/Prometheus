# Dependency Upgrade Workflow

## Overview

The Prometheus dependency upgrade ecosystem implements a guarded, automated loop that ensures reliability, offline parity, performance, and safe, continuous freshness.

## Architecture

### Single Contract

The dependency contract (`configs/dependency-profile.toml`) is the single source of truth. All dependency operations are keyed by contract hash to ensure:

- Deterministic builds across environments
- Cache invalidation when dependencies change
- Audit trail for dependency changes

### Guarded Loop

The upgrade loop follows these stages:

1. **SBOM Generation**: Generate CycloneDX SBOM from current lock
2. **Upgrade Evaluation**: Analyze drift and apply policy gates
3. **Matrix Build**: Build wheelhouse for all platforms using cibuildwheel
4. **Offline Verification**: Test `pip install --no-index --find-links`
5. **Quality Gates**: Run lint, typecheck, tests, coverage, security scans
6. **Promotion**: Promote verified wheelhouse to vendor/

### CI Hardening

#### Quality Gates

Every PR and scheduled run enforces:

- **Linting**: Ruff checks with GitHub-formatted output
- **Type Checking**: (Extensible for mypy/pyright)
- **Tests**: Parallel pytest execution with coverage reporting
- **Coverage**: XML and HTML reports uploaded as artifacts
- **Security**: pip-audit scans with JSON output

#### Caching Strategy

Dependencies are cached using contract hash:

```
Key: {os}-pip-{contract-hash}-{poetry-lock-hash}
Restore Keys:
  - {os}-pip-{contract-hash}-
  - {os}-pip-
```

This ensures:
- Cache invalidation on contract changes
- Warm caches for unchanged dependencies
- Deterministic artifact generation

#### Run Summaries

Each workflow emits structured summaries to `$GITHUB_STEP_SUMMARY`:

- SBOM and contract hashes
- Upgrade evaluation results
- Quality gate status
- Verification results
- Promotion details

### Performance Optimizations

1. **Parallel Tests**: `pytest -n auto` distributes tests across CPUs
2. **Matrix Parallelism**: Platform wheelhouses build concurrently
3. **Warm Caches**: Contract-based caching reduces rebuild time
4. **Deterministic Artifacts**: Stable builds enable better caching

### Freshness & Renovate

Renovate is configured for automated dependency updates with:

- **Schedule**: Weekly (Mondays before 6am UTC)
- **Automerge**: Patch and minor updates that pass quality gates
- **Manual Review**: Major updates require human approval
- **Security Fast-Track**: Security updates merge faster (0 days min age)
- **Status Checks**: All quality gates must pass

Required status checks for automerge:
- `generate-sbom`
- `evaluate-upgrades`
- `quality-gates`
- `verify-offline`

### Observability

#### Health Reports

Each run generates:

1. **Drift Report**: Package-level drift analysis with severity
2. **Assessment Summary**: Upgrade guard aggregated assessment
3. **Quality Status**: Lint, test, coverage, security results
4. **Verification Matrix**: Per-platform offline install results

#### Fail-Fast Policy

Workflows fail immediately on:

- Contract policy violations
- Binary wheel requirements not met (sdist fallback detected)
- Offline verification failures
- Quality gate failures (lint, tests, security)

### Air-Gapped Parity

#### Cross-Platform Verification

The workflow builds and verifies wheelhouses on:

- **Linux**: manylinux2014_x86_64 (Python 3.11, 3.12)
- **macOS**: macosx_14_0_arm64 (Python 3.11, 3.12)
- **Windows**: win_amd64 (Python 3.11, 3.12)

#### Offline Testing

Each platform runs:

```bash
python -m venv /tmp/test-venv
source /tmp/test-venv/bin/activate
pip install --no-index --find-links /tmp/wheelhouse -r /tmp/wheelhouse/requirements.txt
```

This ensures true offline capability before promotion.

#### Checksums & Manifests

Each wheelhouse includes:

- `requirements.txt`: Pinned dependencies
- `platform_manifest.json`: Platform-specific metadata
- `manifest.json`: Combined multi-platform manifest
- SHA256 checksums for all wheels

## Workflows

### dependency-contract-upgrade.yml

Main upgrade orchestration workflow.

**Triggers:**
- Schedule: Nightly at 2am UTC
- Pull requests touching dependencies
- Manual dispatch with force_upgrade option

**Jobs:**
1. `generate-sbom`: Create SBOM from poetry.lock
2. `evaluate-upgrades`: Check drift and apply policy
3. `build-wheelhouse-matrix`: Build for all platforms
4. `verify-offline`: Test offline install on all platforms
5. `quality-gates`: Run full quality suite
6. `promote-wheelhouse`: Aggregate and promote to vendor/
7. `summary`: Generate workflow summary

### ci.yml (Enhanced)

Main CI pipeline with added quality gates.

**Enhancements:**
- Contract hash-based caching
- Parallel quality gates job
- Comprehensive test coverage
- Security scanning
- Step summaries

### dependency-preflight.yml

Existing preflight workflow continues to run for quick validation.

## Usage

### Local Development

Sync dependencies from contract:

```bash
bash scripts/manage-deps.sh
```

Check for upgrades:

```bash
python scripts/dependency_drift.py \
  --sbom var/upgrade-guard/sbom/sbom.json \
  --metadata var/upgrade-guard/metadata/metadata.json \
  --policy configs/dependency-profile.toml
```

Run upgrade guard:

```bash
python scripts/upgrade_guard.py \
  --contract configs/dependency-profile.toml \
  --sbom var/upgrade-guard/sbom/sbom.json \
  --metadata var/upgrade-guard/metadata/metadata.json \
  --output var/upgrade-guard/assessment.json \
  --markdown var/upgrade-guard/summary.md \
  --verbose
```

### CI Integration

The workflow runs automatically on:

1. **Scheduled**: Nightly dependency checks
2. **Pull Requests**: Renovate updates trigger full validation
3. **Manual**: Use workflow_dispatch for ad-hoc checks

### Monitoring

Check workflow summaries in GitHub Actions for:

- Upgrade opportunities detected
- Policy gate decisions
- Quality gate status
- Verification results

## Runbook

### Dependency Update Approval

1. Renovate opens PR with dependency update
2. Post-upgrade tasks regenerate manifests
3. CI runs dependency-contract-upgrade workflow
4. Quality gates execute (lint, test, security)
5. Wheelhouse builds for all platforms
6. Offline verification confirms air-gapped capability
7. If all checks pass and update is patch/minor: **automerge**
8. If major update: requires manual review and approval

### Manual Upgrade

Force an upgrade check:

```bash
gh workflow run dependency-contract-upgrade.yml -f force_upgrade=true
```

### Troubleshooting

#### Wheelhouse Build Failure

Check `allow_sdist_used` in platform manifest:

```bash
jq '.allow_sdist_used' dist/wheelhouse/platform_manifest.json
```

If non-empty, a package requires source build. Options:

1. Add to `policies.sdist_fallback.allow` in contract
2. Wait for upstream wheel release
3. Build custom wheel

#### Offline Verification Failure

Download wheelhouse artifact and test locally:

```bash
python -m venv /tmp/test-venv
source /tmp/test-venv/bin/activate
pip install --no-index --find-links /path/to/wheelhouse -r /path/to/wheelhouse/requirements.txt
```

#### Quality Gate Failure

Check specific gate that failed:

- **Lint**: `poetry run ruff check . --diff`
- **Tests**: `poetry run pytest tests/ -v`
- **Security**: `pip-audit -r <(poetry export --without-hashes)`

### Emergency Override

To bypass automerge for urgent fixes:

1. Add label `hold` to PR
2. Renovate will not automerge
3. Review and merge manually when ready

## References

- [Dependency Contract](../configs/dependency-profile.toml)
- [Dependency Upgrade Architecture](./dependency-upgrade-architecture.md)
- [Upgrade Guard Strategy](./upgrade-guard.md)
- [Renovate Configuration](../renovate.json)
