# Chiron Frontier Standards Implementation Guide

## Overview

This document describes the frontier-standards enhancements made to Chiron, bringing it to production-grade quality across dependency management, autoremediation, GitHub integration, CI wheelbuilding, and air-gapped deployment preparation.

## Core Enhancements

### 1. Intelligent Autoremediation

**Location**: `chiron/remediation/autoremediate.py`

The autoremediation engine provides intelligent, confidence-based fixes for common failures:

#### Supported Failure Types

##### Dependency Sync Failures

- **Symptoms**: `poetry.lock out of date`, version conflicts, missing modules
- **Remediations**:
  - Regenerate Poetry lock file (`poetry lock --no-update`)
  - Reinstall dependencies (`poetry install --sync`)
  - Resolve version conflicts (`poetry update`)
- **Confidence**: 0.7-0.9 (auto-apply eligible)

##### Wheelhouse Build Failures

- **Symptoms**: Missing binary wheels, platform incompatibility
- **Remediations**:
  - Pin to fallback version
  - Suggest wheel build from source
  - Add to `ALLOW_SDIST_FOR` list
- **Confidence**: 0.5-0.85 (mostly manual)

##### Mirror Corruption

- **Symptoms**: Missing index files, incomplete downloads
- **Remediations**:
  - Create mirror directory structure
  - Re-sync from source
  - Rebuild package index
- **Confidence**: 0.8-1.0 (high auto-apply)

##### Artifact Validation Failures

- **Symptoms**: Missing manifests, empty wheelhouse, corrupted archives
- **Remediations**:
  - Regenerate manifest
  - Rebuild wheelhouse
  - Remove and re-download corrupted files
- **Confidence**: 0.6-0.9

##### Configuration Drift

- **Symptoms**: Contract/lock mismatch
- **Remediations**:
  - Auto-sync manifests
  - Force dependency sync
- **Confidence**: 0.85 (auto-apply eligible)

#### Usage

```bash
# Preview actions without applying
chiron remediate auto dependency-sync --input error.log --dry-run

# Auto-apply high-confidence fixes
chiron remediate auto wheelhouse --input wheelhouse-failures.json --auto-apply

# Manual review mode (default)
chiron remediate auto artifact --input validation.json
```

#### Programmatic API

```python
from chiron.remediation.autoremediate import AutoRemediator

remediator = AutoRemediator(dry_run=False, auto_apply=True)

# Remediate dependency sync failure
result = remediator.remediate_dependency_sync_failure(error_log)

# Check results
if result.success:
    print(f"Applied: {result.actions_applied}")
else:
    print(f"Failed: {result.actions_failed}")
    print(f"Errors: {result.errors}")
```

---

### 2. Air-Gapped Preparation Workflow

**Location**: `chiron/orchestration/coordinator.py` → `air_gapped_preparation_workflow`

Complete 6-step workflow for offline deployment preparation:

#### Workflow Steps

1. **Full Dependency Management** (preflight → guard → sync)
   - Validates dependency health
   - Runs upgrade guard checks
   - Syncs contracts to manifests

2. **Multi-Platform Wheelhouse Building**
   - Builds wheels for all dependencies
   - Includes development dependencies
   - Validates wheel availability

3. **Model Downloads**
   - Sentence-Transformers embeddings
   - spaCy language models
   - Hugging Face models (if configured)

4. **Container Image Preparation** (optional)
   - Docker/Podman image exports
   - Container registry caching

5. **Complete Offline Packaging**
   - Aggregates all artifacts
   - Generates checksums (SHA256)
   - Creates comprehensive manifests

6. **Comprehensive Validation**
   - Validates package completeness
   - Checks artifact integrity
   - Runs offline doctor diagnostics
   - Auto-remediation on failures

#### Usage

```bash
# Full air-gapped preparation
chiron orchestrate air-gapped-prep

# Skip models (faster for dependency-only updates)
chiron orchestrate air-gapped-prep --no-models

# Include container images
chiron orchestrate air-gapped-prep --containers

# Dry-run to preview steps
chiron orchestrate air-gapped-prep --dry-run --verbose
```

#### Output Structure

```
vendor/offline/
├── wheelhouse/
│   ├── *.whl                 # All Python wheels
│   ├── manifest.json         # Wheel metadata
│   └── requirements.txt      # Pinned versions
├── models/
│   ├── sentence-transformers/
│   ├── spacy/
│   └── huggingface/
├── containers/
│   └── *.tar.gz              # Exported images
├── checksums.sha256          # All artifact checksums
└── package-manifest.json     # Complete inventory
```

---

### 3. GitHub Actions Artifact Sync

**Location**: `chiron/github/sync.py`

Seamless integration with GitHub Actions for CI-built artifacts.

#### Features

- Download artifacts from specific workflow runs
- Validate artifact structure and integrity
- Sync to local directories (vendor/, dist/, var/)
- Support for multiple artifact types:
  - `wheelhouse-linux`, `wheelhouse-macos`, `wheelhouse-windows`
  - `offline-packaging-suite`
  - `models-cache`
  - `dependency-reports`

#### Usage

```bash
# Download and sync artifacts from a workflow run
chiron github sync 12345678 --sync-to vendor --validate

# Download specific artifacts only
chiron github sync 12345678 \
  --artifact wheelhouse-linux \
  --artifact models-cache \
  --output-dir ./artifacts

# Validate existing artifacts
chiron github validate ./artifacts/wheelhouse-linux --type wheelhouse
```

#### Programmatic API

```python
from chiron.github import GitHubArtifactSync

syncer = GitHubArtifactSync(repo="owner/repo")

# Download artifacts
result = syncer.download_artifacts(
    run_id="12345678",
    artifact_names=["wheelhouse-linux", "models-cache"],
)

# Validate
validation = syncer.validate_artifacts(
    Path("artifacts/wheelhouse-linux"),
    artifact_type="wheelhouse",
)

# Sync to vendor/
syncer.sync_to_local(
    Path("artifacts/wheelhouse-linux"),
    target="vendor",
    merge=False,
)
```

---

### 4. Enhanced Dependency Management

#### Dependency Mirror Management

**Location**: `chiron/deps/mirror_manager.py`

Local PyPI mirror management for air-gapped environments:

```bash
# Check mirror status
python -m chiron.deps.mirror_manager --status

# Update mirror from wheelhouse
python -m chiron.deps.mirror_manager \
  --update \
  --source vendor/wheelhouse \
  --mirror-root vendor/mirror

# Prune outdated packages
python -m chiron.deps.mirror_manager --update --prune
```

#### Dependency Drift Detection

Enhanced drift detection with auto-remediation:

```bash
# Detect drift
chiron deps drift

# Auto-remediate drift
chiron remediate auto drift --input drift-report.json --auto-apply
```

---

## Integration with CI/CD

### GitHub Actions Workflow Integration

#### Offline Packaging Workflow

```yaml
name: Offline Packaging

jobs:
  build-wheels:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/checkout@v5
      - uses: ./.github/actions/setup-python-poetry

      # Build multi-platform wheels with cibuildwheel
      - name: Build wheels
        env:
          CIBW_BUILD: "cp311-* cp312-*"
        run: cibuildwheel --output-dir wheelhouse

      - uses: actions/upload-artifact@v4
        with:
          name: wheelhouse-${{ runner.os }}
          path: wheelhouse/

  package:
    needs: build-wheels
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      # Download all platform wheels
      - uses: actions/download-artifact@v4
        with:
          pattern: wheelhouse-*
          path: vendor/wheelhouse

      # Run air-gapped preparation
      - name: Air-gapped preparation
        run: |
          poetry run chiron orchestrate air-gapped-prep \
            --validate \
            --verbose

      # Upload complete package
      - uses: actions/upload-artifact@v4
        with:
          name: offline-packaging-suite
          path: vendor/offline/
```

#### Consuming CI Artifacts Locally

```bash
# Download artifacts from latest successful run
gh run list --workflow offline-packaging --limit 1 --json databaseId --jq '.[0].databaseId'

# Sync to local environment
chiron github sync <run-id> --sync-to vendor --validate

# Validate and use
chiron doctor offline --package-dir vendor/offline
```

---

## Best Practices

### 1. Dependency Management

- Run `chiron deps preflight` before any dependency changes
- Use `chiron deps guard` to catch breaking upgrades
- Always sync after contract updates: `chiron deps sync --apply`
- Monitor drift weekly: `chiron deps drift`

### 2. Wheelhouse Building

- Build for all target platforms using cibuildwheel
- Validate wheels immediately: `chiron doctor offline`
- Keep fallback versions for problematic packages
- Run remediation on failures: `chiron remediate wheelhouse`

### 3. Air-Gapped Deployments

- Use `chiron orchestrate air-gapped-prep` for complete preparation
- Validate package before deployment
- Keep checksums for integrity verification
- Test installation in clean environment

### 4. Autoremediation

- Start with `--dry-run` to preview actions
- Use `--auto-apply` only for high-confidence fixes
- Review action history after remediation
- Keep rollback commands available

### 5. GitHub Integration

- Sync artifacts after each successful CI run
- Validate before local use
- Use merge mode for incremental updates
- Monitor artifact storage limits

---

## Troubleshooting

### Common Issues

#### Autoremediation Not Applying Fixes

**Problem**: Actions shown as "skipped" or "low confidence"

**Solution**:

```bash
# Check action history
chiron remediate auto <type> --input <file> --dry-run --verbose

# Force auto-apply (use with caution)
chiron remediate auto <type> --input <file> --auto-apply
```

#### GitHub Artifact Download Fails

**Problem**: `gh` CLI not available or authentication failed

**Solution**:

```bash
# Install GitHub CLI
brew install gh  # macOS
sudo apt install gh  # Ubuntu

# Authenticate
gh auth login
```

#### Air-Gapped Workflow Fails at Models Step

**Problem**: Model downloads timeout or fail

**Solution**:

```bash
# Skip models and download separately
chiron orchestrate air-gapped-prep --no-models

# Download models separately with retries
chiron doctor models --verbose --retry 3
```

#### Wheelhouse Validation Fails

**Problem**: "No wheel files found" or manifest errors

**Solution**:

```bash
# Check wheelhouse structure
ls -la vendor/wheelhouse/

# Regenerate manifest
chiron package offline --manifest-only

# Run remediation
chiron remediate wheelhouse \
  --log build-logs.txt \
  --output remediation.json
```

---

## Performance Considerations

### Air-Gapped Preparation

- **Duration**: 20-45 minutes (full workflow)
  - Dependencies: 2-5 min
  - Wheelhouse: 5-15 min
  - Models: 10-20 min
  - Validation: 2-5 min

- **Storage**: 2-10 GB (depends on model selection)
  - Wheelhouse: 500 MB - 2 GB
  - Models: 1-8 GB
  - Containers: 1-5 GB (if included)

### Optimization Tips

1. **Incremental Updates**: Use `--merge` when syncing artifacts
2. **Selective Models**: Skip unnecessary models with `--no-models`
3. **Parallel Downloads**: GitHub CLI supports concurrent artifact downloads
4. **Caching**: Leverage Poetry cache and GitHub Actions cache

---

## Migration from Legacy Scripts

### Script Mapping

| Legacy Script                 | New Chiron Command         |
| ----------------------------- | -------------------------- |
| `scripts/build-wheelhouse.sh` | `chiron package offline`   |
| `scripts/verify_artifacts.sh` | `chiron github validate`   |
| `scripts/offline_doctor.py`   | `chiron doctor offline`    |
| `scripts/manage-deps.sh`      | `chiron deps sync --apply` |
| Manual remediation            | `chiron remediate auto`    |
| Manual CI artifact download   | `chiron github sync`       |

### Migration Checklist

- [ ] Update CI workflows to use `chiron orchestrate` commands
- [ ] Replace script calls with `chiron` CLI equivalents
- [ ] Update documentation references
- [ ] Test air-gapped workflow end-to-end
- [ ] Configure autoremediation for CI pipelines
- [ ] Set up GitHub artifact sync automation

---

## References

- [Chiron README](./README.md) - Overview and architecture
- [Migration Guide](./MIGRATION_GUIDE.md) - Detailed migration instructions
- [Quick Reference](./QUICK_REFERENCE.md) - Command cheat sheet
- [cibuildwheel Integration](../cibuildwheel-integration.md) - Multi-platform wheels
- [Workflow Orchestration](../workflow-orchestration.md) - CI/CD patterns
