# CI Packaging Workflow Quick Reference

This document provides a quick reference for the automated packaging workflow
that prevents issues like PR #90 (wheelhouse with metadata but no actual wheel
files).

## Automated CI Packaging

Every push to `main` and pull request automatically:

1. **Builds Python wheel** from the project source
2. **Generates complete wheelhouse** with all dependencies:
   - Main dependencies
   - All extras (pii, observability, rag, llm, governance, integrations)
   - Development dependencies
   - pip-audit for offline security scanning
3. **Validates artifacts** before upload:
   - Checks for actual .whl files (not just metadata)
   - Verifies requirements.txt and manifest.json
   - Confirms pip-audit is included
4. **Uploads to GitHub Actions** as `app_bundle` artifact (30-day retention)
5. **Tests in consumer job** (simulates air-gapped environment):
   - Downloads artifact
   - Runs comprehensive verification
   - Tests offline installation
   - Confirms pip-audit availability

## How to Access CI-Built Artifacts

### Via GitHub UI

1. Go to repository Actions tab
2. Click on the workflow run for your commit
3. Scroll to "Artifacts" section
4. Download `app_bundle` artifact
5. Extract: `unzip app_bundle.zip`
6. Artifacts are in `dist/` directory

### Via GitHub CLI

```bash
# List recent workflow runs
gh run list --limit 5

# Download artifact from specific run
gh run download <run-id> --name app_bundle

# Or download from latest main branch run
gh run download --branch main --name app_bundle
```

## Validating Downloaded Artifacts

Use the provided verification script:

```bash
# Basic validation
bash scripts/verify_artifacts.sh dist/

# With detailed output
VERBOSE=true bash scripts/verify_artifacts.sh dist/

# With offline installation test
bash scripts/verify_artifacts.sh dist/ --test
```

### Manual Validation Checklist

```bash
# 1. Check directory structure
ls -la dist/
ls -la dist/wheelhouse/

# 2. Verify wheel files exist
find dist/wheelhouse -name "*.whl" | wc -l  # Should be > 0

# 3. Check manifest
cat dist/wheelhouse/manifest.json

# 4. Verify requirements
head dist/wheelhouse/requirements.txt

# 5. Check for pip-audit
ls dist/wheelhouse/pip_audit*.whl

# 6. Test offline install
python -m venv test-venv
source test-venv/bin/activate
python -m pip install --no-index \
  --find-links dist/wheelhouse \
  -r dist/wheelhouse/requirements.txt
pip-audit --version
deactivate
rm -rf test-venv
```

## Troubleshooting

### Problem: No wheels in wheelhouse

**Symptom**: `find dist/wheelhouse -name "*.whl"` returns nothing

**Cause**: This is the PR #90 issue - build failed or poetry export failed

**Solution**:

1. Check workflow logs for errors in "Build wheelhouse" step
2. Verify poetry-plugin-export is installed
3. Ensure poetry.lock is up to date
4. Re-run the workflow

### Problem: Offline install fails

**Symptom**: `pip install --no-index` fails with missing dependencies

**Cause**: Some dependencies weren't captured in the wheelhouse

**Solution**:

1. Check which dependencies are missing from error message
2. Add missing dependencies to pyproject.toml
3. Run `poetry lock`
4. Commit and push - CI will rebuild wheelhouse

### Problem: pip-audit not available

**Symptom**: `pip-audit --version` fails after offline install

**Cause**: pip-audit wheel wasn't included in build

**Solution**:

1. Check workflow logs for pip-audit download errors
2. Verify "Build wheelhouse" step includes pip-audit
3. Re-run workflow

## CI Workflow Jobs

### build

- Checks out repository
- Installs Python and Poetry
- Builds Python wheel
- Generates wheelhouse with all dependencies
- Validates artifacts (prevents PR #90 issue)
- Uploads `app_bundle` artifact

### consume

- Simulates air-gapped/restricted environment
- Downloads `app_bundle` artifact
- Runs comprehensive verification
- Tests offline installation
- Validates pip-audit availability

### publish

- Builds container image (if Docker available)
- Pushes to GitHub Container Registry

### cleanup

- Keeps last 5 `app_bundle` artifacts
- Deletes older artifacts to manage storage

## Key Files

- `.github/workflows/ci.yml` - Main CI workflow with packaging
- `scripts/build-wheelhouse.sh` - Wheelhouse generation script
- `scripts/verify_artifacts.sh` - Artifact validation script
- `scripts/offline_doctor.py` - Pre-flight checks for offline packaging
- `vendor/wheelhouse/` - Local wheelhouse (tracked with Git LFS)
- `CI/README.md` - Detailed CI pipeline documentation

## Integration with Development Workflow

### Local Development

When developing locally, you can:

1. Build wheelhouse manually: `bash scripts/build-wheelhouse.sh`
   - On failure, review `vendor/wheelhouse/remediation/wheelhouse-remediation.json`
     for automated guidance on missing wheels and suggested fallbacks.
2. Validate local wheelhouse: `bash scripts/verify_artifacts.sh vendor/`
3. Use CI-built wheelhouse: Download from Actions and extract to `vendor/`

### Air-Gapped Deployment

For deploying to air-gapped environments:

1. Download latest `app_bundle` from Actions
2. Transfer to air-gapped environment
3. Run verification: `bash scripts/verify_artifacts.sh dist/`
4. Install: `pip install --no-index --find-links dist/wheelhouse -r dist/wheelhouse/requirements.txt`

## Best Practices

1. **Always validate artifacts** before deploying to production
2. **Check workflow logs** if artifact seems incomplete
3. **Keep poetry.lock up to date** to ensure consistent dependencies
4. **Test offline install** before relying on wheelhouse in air-gapped env
5. **Monitor CI workflow failures** and fix issues promptly
6. **Document any custom packaging requirements** in this file

## Related Documentation

- [CI/README.md](../CI/README.md) - Complete CI pipeline documentation
- [docs/developer-experience.md](developer-experience.md) - Developer workflow guide
- [docs/offline-bootstrap-gap-analysis.md](offline-bootstrap-gap-analysis.md) -
  PR #90 analysis

## Questions?

For issues or questions about the CI packaging workflow:

1. Check troubleshooting section above
2. Review workflow logs in Actions tab
3. Consult CI/README.md for detailed documentation
4. Open an issue with `ci` label
