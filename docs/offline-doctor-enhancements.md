# Offline Doctor Enhancements

This document describes the enhancements made to the offline doctor diagnostic
tool (`scripts/offline_doctor.py`) to provide comprehensive project health
checks and prevent packaging failures.

## Overview

The offline doctor tool diagnoses the offline packaging environment and reports
on the health of all critical components needed for successful offline package
generation.

## What's New

### Multiple Output Formats

The doctor now supports three output formats:

1. **JSON** (`--format json` or `--json`): Machine-readable output for
   automation
2. **Table** (`--format table`): Rich formatted table with status symbols
3. **Text** (`--format text`): Traditional logging output (default)

Example usage:

```bash
# Recommended: Use via the CLI proxy
prometheus offline-doctor --format table

# Alternative: Direct script invocation
python scripts/offline_doctor.py --format table

# JSON format (for CI/automation)
prometheus offline-doctor --format json

# Text format (default, traditional logging)
prometheus offline-doctor
```

### Enhanced Diagnostics

The doctor now checks:

#### Tool Availability

- **Python**: Version check and executable location
- **pip**: Version check and minimum version enforcement
- **Poetry**: Binary availability and version check
- **Docker**: Availability and version (if container images configured)

#### Project Context

- **Git Repository Status**:
  - Current branch and commit
  - Uncommitted changes count
  - Git LFS availability and tracked files
- **Disk Space**:
  - Total, used, and free space in GB
  - Usage percentage
  - Warnings for low disk space (<5 GB)
  - Errors for critical low space (<1 GB)

- **Build Artifacts**:
  - `dist/` directory existence
  - Wheel count in dist root
  - Wheelhouse directory status
  - Wheels in wheelhouse count
  - Manifest and requirements file presence

- **Dependencies**:
  - `pyproject.toml` presence
  - `poetry.lock` presence
  - Lock file age (warns if >90 days old)

#### Wheelhouse Audit

- Active requirements count
- Missing wheels detection
- Orphan artifacts detection
- Removed orphans tracking

## Using in CI

The doctor is integrated into the CI workflow to validate the packaging
environment before building artifacts:

```yaml
- name: Validate offline package
  run: |
    poetry run python scripts/offline_doctor.py --format table || {
      echo "::warning::Offline package validation had warnings"
    }
```

This helps catch issues early:

- Missing dependencies
- Tool version mismatches
- Low disk space
- Missing build artifacts
- Git repository issues

## Exit Codes

The doctor always returns 0 (success) but outputs warnings and errors in the
diagnostics. This allows CI workflows to continue even with warnings while still
logging the issues for review.

To fail on errors, parse the output:

```bash
python scripts/offline_doctor.py --format json > diagnostics.json
if jq '.[] | select(.status == "error")' diagnostics.json | grep -q .; then
    echo "Errors detected in diagnostics"
    exit 1
fi
```

## Table Format Example

```text
╔══════════════════════════════════════════════════════════════╗
║           Offline Packaging Diagnostic Report               ║
╚══════════════════════════════════════════════════════════════╝

Repository: /path/to/Prometheus
Config:     /path/to/config.toml
Generated:  2025-09-30T12:00:00Z

┌─────────────────┬──────────┬────────────────────┬─────────────────────┐
│ Component       │ Status   │ Version            │ Notes               │
├─────────────────┼──────────┼────────────────────┼─────────────────────┤
│ python          │ ✓ ok     │ 3.12.3             │                     │
│ pip             │ ✓ ok     │ 25.2               │                     │
│ poetry          │ ✓ ok     │ 2.2.1              │                     │
│ docker          │ ✓ ok     │ 28.0.4             │                     │
└─────────────────┴──────────┴────────────────────┴─────────────────────┘

Git Repository:
  Branch:    main
  Commit:    abc123de
  Uncommitted changes: 0
  LFS tracked files:   5

Disk Space: ✓
  Total: 100.0 GB
  Used:  50.0 GB (50.0%)
  Free:  50.0 GB

Build Artifacts:
  Dist directory:        True
  Wheels in dist:        1
  Wheelhouse exists:     True
  Wheels in wheelhouse:  150
  Manifest exists:       True
  Requirements exists:   True

Dependencies: ✓
  pyproject.toml: True
  poetry.lock:    True
  Lock age:       2.5 days

Wheelhouse Audit: ✓ ok

Allowlisted sdists: ⚠ warning
  Note: Allowlisted dependencies rely on sdist fallbacks;
        investigate wheel availability.
  Packages: 1
    - llama-cpp-python==0.3.2 (targets: py3.12@manylinux2014_x86_64)
  Summary path: vendor/wheelhouse/allowlisted-sdists.json

✅ ALL CHECKS PASSED - System ready for offline packaging
```

## Status Symbols

- ✓ (ok): Component is healthy
- ⚠ (warning): Component works but may need attention
- ✗ (error): Component is missing or misconfigured
- ○ (skipped): Check was skipped (not required)
- ? (unknown): Unable to determine status

## Future Enhancements

Potential additions not yet implemented:

1. Network connectivity checks (should be offline in air-gapped mode)
2. Certificate validation for internal registries
3. Model file integrity checks (hash validation)
4. Security vulnerability scanning results summary
5. Historical diagnostics comparison (track changes over time)
6. Automatic remediation suggestions
7. Interactive mode for guided troubleshooting

## Allowlisted Sdist Tracking

The dependency preflight guard now writes a machine-readable summary to
`vendor/wheelhouse/allowlisted-sdists.json` during every run of
`scripts/manage-deps.sh`. The offline doctor loads the same artefact and
displays any packages that still rely on the sdist allowlist. Teams should use
that list to decide whether to upstream a wheel build, pin an alternative
distribution, or keep the exception documented in the configuration.

## Dependency Preflight Execution

Offline packaging now runs `scripts/preflight_deps.py` automatically during the
dependencies phase. The orchestrator captures the JSON summary, logs any gaps
or allowlisted fallbacks, and blocks packaging if mandatory wheels are missing.
Results are surfaced in both CLI output and doctor diagnostics under
`dependency_preflight`, giving operators early visibility into wheel coverage
issues before the build progresses to artifact creation.

## Related Documentation

- [PR #90 Remediation Summary](./pr90-remediation-summary.md): Context for why
  these enhancements were needed
- [CI Pipeline Documentation](../CI/README.md): How doctor integrates with CI
- [CI Delivery & Packaging Handbook](./ci-handbook.md): Consolidated CI
  automation, artifact validation, and troubleshooting guide

## API Usage

The doctor can be used programmatically:

```python
from prometheus.packaging import OfflinePackagingOrchestrator, load_config

config = load_config()
orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=".")
diagnostics = orchestrator.doctor()

# Check specific components
if diagnostics["pip"]["status"] != "ok":
    print(f"pip issue: {diagnostics['pip'].get('message')}")

# Check for any errors
has_errors = any(
    diag.get("status") == "error"
    for diag in diagnostics.values()
    if isinstance(diag, dict)
)
```

## Troubleshooting

### Doctor Fails to Run

**Symptom**: `ModuleNotFoundError: No module named 'prometheus'`

**Solution**: Run with Poetry or set PYTHONPATH:

```bash
poetry run python scripts/offline_doctor.py --format table
# OR
PYTHONPATH=. python scripts/offline_doctor.py --format table
```

### Poetry Not Found

**Symptom**: `Poetry binary 'poetry' not found in PATH`

**Solution**: Install Poetry or enable auto_install in config:

```bash
pip install poetry==2.2.1
# OR update config
[poetry]
auto_install = true
```

### Low Disk Space Warnings

**Symptom**: `Warning: Less than 5 GB free`

**Solution**:

1. Clean up old build artifacts: `rm -rf dist/ vendor/wheelhouse/`
2. Clean Docker images: `docker system prune -a`
3. Clean pip cache: `pip cache purge`

### Missing Build Artifacts

**Symptom**: `No build artifacts found`

**Solution**: Run the build process:

```bash
poetry build
bash scripts/build-wheelhouse.sh dist/wheelhouse
```

### Old Lock File Warning

**Symptom**: `Lock file is 120 days old`

**Solution**: Update dependencies:

```bash
poetry update
poetry lock --no-update  # If you just want to refresh lock
```
