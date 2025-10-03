# CI Delivery & Packaging Handbook

## Overview

This handbook consolidates the CI workflow comparison, packaging quick
reference, and CLI integration summary into a single guide. Use it to
understand what changed in the packaging pipeline, how to consume build
artefacts, and which commands keep air-gapped environments healthy.

## Workflow improvements at a glance

### Before

```yaml
- name: Install build dependencies
  run: |
    python -m pip install --upgrade pip
    pip install build wheel poetry==2.2.1 poetry-plugin-export
    # No verification of installation success
    # No check if Poetry is in PATH
```

#### Issues

- Poetry availability was never verified.
- Disk space and wheelhouse health checks were missing.
- Offline doctor lacked the `--format` flag, causing validation failures.
- Packaging artefacts could ship without accompanying wheels (PR #90).

### After

```yaml
- name: Install build dependencies
  run: |
    python -m pip install --upgrade pip
    pip install build wheel poetry==2.2.1 poetry-plugin-export || {
      echo "::error::Failed to install build dependencies"
      exit 1
    }

    python -m pip --version
    poetry --version || echo "::warning::Poetry not in PATH"
    poetry-plugin-export --version 2>/dev/null || {
      echo "::warning::poetry-plugin-export may not be installed"
    }
```

#### Fixes

- Verified toolchain and surfaced missing dependencies early.
- Added disk space checks before wheelhouse builds.
- Enhanced offline doctor with table/text/JSON output and CLI proxy.
- Introduced artifact validation and remediation scripts in CI.

## End-to-end packaging workflow

1. **Doctor** — `prometheus offline-doctor [--format table|json|text]`
   validates Python, pip, Poetry, Docker, wheelhouse health, Git status, and
   disk space before packaging.
2. **Package** — `prometheus offline-package` orchestrates cleanup,
   dependencies, models, containers, checksums, and git hygiene. Use
   `--auto-update` to enable safe automatic upgrades.
3. **Status** — `prometheus deps status [--json --output <path>]` aggregates
   guard, planner, and remediation signals with optional Markdown summaries.
4. **Upgrade** — `prometheus deps upgrade --sbom <path> [--apply --yes]`
   generates weighted upgrade plans and optionally applies them.
5. **Guard** — `prometheus deps guard` enforces contract policy during CI and
   blocks merges when severity exceeds the configured threshold.
6. **Mirror** — `prometheus deps mirror --status|--update` reports wheelhouse
   hygiene and promotes new artefacts.
7. **Verify** — `bash scripts/verify_artifacts.sh dist/ [--test]` ensures
   packaged artefacts contain wheels, manifests, requirements, and `pip-audit`.

## Accessing CI-built artefacts

### GitHub UI

1. Open the Actions tab and select the relevant workflow run.
2. Download the `app_bundle` artifact.
3. Extract the zip (`unzip app_bundle.zip`) to inspect `dist/` contents.

### GitHub CLI

```bash
# List recent runs
gh run list --limit 5

# Download the latest main run artefact
gh run download --branch main --name app_bundle

# Download from a specific run ID
gh run download <run-id> --name app_bundle
```

## Validation & troubleshooting

- Run `bash scripts/verify_artifacts.sh dist/ --test` to confirm wheels exist,
  requirements are synced, and an offline installation succeeds.
- Manually check wheel presence with
  `find dist/wheelhouse -name "*.whl" | wc -l` (should be > 0).
- Ensure `pip-audit` ships by verifying
  `ls dist/wheelhouse/pip_audit*.whl`.
- If the offline install fails, update `pyproject.toml`, rerun `poetry lock`,
  and trigger the workflow again.
- Review workflow logs whenever artifact validation emits warnings.

## Integrated CLI flow

- `prometheus offline-doctor` is now a first-class CLI proxy with tests for
  argument forwarding and exit propagation.
- Command docstrings within `prometheus/cli.py` cross-reference the wider
  workflow (doctor → package → status → upgrade → package) so the help output
  forms a built-in runbook.
- Observability hooks record spans and counters for each dependency command,
  feeding the dashboards defined in `docs/observability.md`.

## Recommended runbooks

1. **Pre-packaging health check**
   - Run `prometheus offline-doctor --format table`.
   - Execute `prometheus offline-package --dry-run` if high-risk changes are
     pending.
   - Review guard status via `prometheus deps status --json`.
2. **Dependency update cycle**
   - `prometheus deps status`
   - `prometheus deps upgrade --sbom var/dependency-sync/sbom.json`
   - `prometheus offline-package`
   - `prometheus offline-doctor`
3. **CI verification pattern**
   - `dependency-preflight.yml` performs guard checks, snapshot scheduling, and
     wheel availability validation.
   - `ci.yml` builds the wheelhouse, runs consumer simulations, and uploads
     `app_bundle` artefacts.
   - `offline-packaging-optimized.yml` refreshes the wheelhouse on demand with
     caching and LFS hygiene.
4. **Air-gapped deployment**
   - Download the latest `app_bundle`.
   - Transfer artefacts via removable media.
   - Run `scripts/bootstrap_offline.py --wheelhouse-url file:///path`.
   - Validate with `prometheus offline-doctor` and `scripts/verify_artifacts.sh`.

## Future enhancements

- Automate shell completions and command aliases for frequent packaging flows.
- Add end-to-end CLI smoke tests once Poetry dependencies are installed in CI.
- Extend dashboards with planner success rate, schedule lag, and CLI adoption
  metrics.
- Explore dry-run visualisation modes and interactive remediation prompts to
  help non-technical operators resolve guard escalations.
