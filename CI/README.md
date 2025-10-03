# CI Pipeline Documentation

This document explains the dual-environment CI pipeline that works on both
GitHub.com and GitHub Enterprise Server (GHES) in air-gapped deployments.

> **Note**: For comprehensive workflow orchestration details including cross-cutting
> concerns and coordination patterns, see [docs/workflow-orchestration.md](../docs/workflow-orchestration.md).

## Overview

The CI pipeline automatically detects its environment via `$GITHUB_SERVER_URL`
and adapts its behavior for registry endpoints, artifact handling, and caching
strategies. It consists of six main jobs:

1. **workflow-lint** – Prefers Trunk-managed `actionlint` and `shellcheck`,
   but automatically falls back to portable binaries when Trunk is
   unavailable, ensuring the lint gate still runs on air-gapped runners
2. **build** – Checkout, build Python wheel, create wheelhouse with all
   dependencies (including pip-audit), validate health, and upload artifacts
3. **publish** – Build and push container images (conditional on Docker
   availability)
4. **consume** – Download artifacts and demonstrate installation including
   offline wheelhouse testing (simulates restricted runners)
5. **cleanup** – Prune old artifacts to manage storage (keeps last 5 builds)
6. **dependency-check** – Check for outdated dependencies (runs on schedule)

### Workflow lint guardrails

Trunk CLI is vendored in `.trunk/tools/trunk` and configured via
`.trunk/trunk.yaml`. When available, the lint job invokes
`./.trunk/tools/trunk check --ci --filter=actionlint,shellcheck`, ensuring the
same pinned toolchain (actionlint 1.7.7 and shellcheck 0.11.0) that developers
use locally. If Trunk is absent (for example on fully air-gapped GHES runners),
the workflow automatically falls back to `scripts/ci/install-actionlint.sh`
which either uses a pre-seeded binary in `vendor/tooling/actionlint` or, when
egress is allowed, downloads the official release. Shell linting then executes
via the system `shellcheck` binary, allowing the lint gate to run without Trunk
support.

The build job now includes comprehensive offline packaging support with health
checks:

- Generates complete wheelhouse with all project dependencies
- Includes pip-audit for offline security scanning
- Creates manifest with metadata about included wheels
- **Validates environment health before building** (new)
- **Checks disk space availability** (new)
- **Validates Poetry installation and version** (new)
- Validates wheelhouse before upload to catch issues early
- Tests offline installation in consume job

## Health Checks

The CI workflow now includes comprehensive health checks to prevent failures:

### Pre-Build Health Checks

- **Tool Availability**: Verifies pip, Poetry, and poetry-plugin-export are
  installed
- **Disk Space**: Warns if less than 5GB free space available
- **Poetry Verification**: Ensures Poetry is in PATH and working

### Post-Build Validation

- **Offline Doctor**: Runs comprehensive diagnostics using `offline_doctor.py
--format table`
  - Checks all tool versions
  - Verifies Git repository state
  - Reports disk space status
  - Validates build artifacts
  - Checks dependency health
- **Artifact Verification**: Uses `verify_artifacts.sh` to ensure wheelhouse
  has actual wheels
- **Offline Install Test**: Simulates air-gapped installation in consume job

See [Offline Doctor Enhancements](../docs/offline-doctor-enhancements.md) for
details on the diagnostic tool.

## Environment Detection

The pipeline detects whether it's running on GitHub.com or GHES by examining
`$GITHUB_SERVER_URL`:

- **GitHub.com**: `https://github.com` → uses `ghcr.io` registry
- **GHES**: Any other URL (e.g., `https://github.example.com`) → derives
  registry as `containers.<hostname>`

This logic is implemented in the `build` job's `env-detect` step and shared
with downstream jobs via outputs.

## Registry Endpoints

### GitHub.com

- Registry: `ghcr.io`
- Authentication: `GITHUB_TOKEN` with `packages: write` permission
- Image tag format: `ghcr.io/<owner>/<repo>/app:<sha>`

### GHES (Air-gapped)

- Registry: `containers.<hostname>` (e.g., `containers.github.example.com`)
- Authentication: `GITHUB_TOKEN` with appropriate GHES permissions
- Image tag format: `containers.<hostname>/<owner>/<repo>/app:<sha>`

The registry endpoint is automatically derived; no manual configuration is
needed unless you override the `REGISTRY` secret.

## Artifact Handling

### Build Artifacts

The `build` job packages deliverables into `./dist` and uploads them using
`actions/upload-artifact@v4`:

- **Artifact name**: `app_bundle`
- **Retention**: 30 days (configurable via `RETENTION_DAYS` env var)
- **Contents**:
  - Python wheel (`.whl`) built from the project
  - Complete wheelhouse directory with all dependencies
  - Build metadata (`BUILD_INFO`)
  - Wheelhouse manifest with dependency list and metadata

### Wheelhouse for Offline Installation

The wheelhouse is automatically generated during the build job with:

- All project dependencies (main + extras)
- Development dependencies (for complete offline development)
- pip-audit tool for offline security scanning
- Platform-specific wheels for the build environment
- `requirements.txt` for simplified offline installation
- `manifest.json` with metadata about the wheelhouse contents

This ensures that air-gapped or restricted environments can install all
dependencies without internet access using:

```bash
python -m pip install --no-index \
  --find-links dist/wheelhouse \
  -r dist/wheelhouse/requirements.txt
```

### Large Payloads (>2 GiB)

If your build produces artifacts exceeding ~2 GiB, consider:

1. **Multi-part archives**: Split large files before upload using `split`
   command
2. **Container images**: Push large assets as OCI images instead (handled by
   `publish` job)
3. **External storage**: Use S3/blob storage with signed URLs and store only
   the manifest in artifacts
4. **Git LFS**: For wheelhouse and model files, use Git LFS to track them in
   the repository (configured in `.gitattributes`)

The current implementation prioritizes artifacts for smaller payloads and
container images for long-lived or large assets. The wheelhouse is tracked
with Git LFS when committed to the repository.

## Air-gapped Safety

### Marketplace Actions

The pipeline uses only GitHub-official actions that are typically mirrored in
GHES environments:

- `actions/checkout@v5`
- `actions/setup-python@v5`
- `actions/upload-artifact@v4`
- `actions/download-artifact@v4`

For Docker login, we use a native shell script (`scripts/ci/docker-login.sh`)
instead of `docker/login-action@v3` to ensure compatibility in air-gapped
setups where Marketplace actions may be unavailable.

### Network Fetches

The pipeline avoids network fetches for toolchains by:

- Using pre-seeded runner tool caches (Python via `actions/setup-python@v5`)
- Checking for local pip cache availability before enabling cache actions
- Gracefully skipping Docker operations if the daemon is unavailable

### Dependency Caching

Language-aware caching (pip) is conditional and uses `actions/cache@v4`:

- **Enabled**: When running on GitHub Actions (not local testing)
- **Cache key**: Based on `poetry.lock` and `pyproject.toml` hashes
- **Paths**: `~/.cache/pip` and `~/.local/share/pip`
- **Fallback**: Continues without cache if unavailable (air-gapped safety)

This prevents internet pulls in restricted environments while still providing
performance benefits when caching is available.

### Poetry Integration

Since this is a Poetry project, the build job uses Poetry for dependency
management:

- Installs `poetry==2.2.1` for consistency
- Runs `poetry install --no-root --only main` for dependencies
- Uses `poetry build` for creating wheel distributions
- Falls back to `python -m build` if Poetry unavailable

### Dependency Update Intelligence

The pipeline includes a `dependency-check` job that:

- Runs weekly on Mondays at 9:00 UTC (via schedule trigger)
- Can be triggered manually via workflow_dispatch
- Checks for outdated dependencies using `poetry show --outdated`
- Generates a summary report in the workflow summary
- Uploads dependency report as an artifact (7-day retention)

This helps maintain awareness of available updates without automatically
applying them (conservative approach).

### Artifact Cleanup

The `cleanup` job automatically prunes old artifacts:

- Runs after all other jobs complete
- Keeps the last 5 `app_bundle` artifacts
- Only runs on main branch (skips PR builds)
- Uses `actions/github-script@v7` for artifact management
- Continues on error to avoid blocking the workflow

## Container Publishing

The `publish` job builds and pushes container images, but it's designed to be
**idempotent and conservative**:

1. **Docker check**: Verifies `docker` command is available; skips if not
2. **Login fallback**: Uses native `docker login` via
   `scripts/ci/docker-login.sh` for GHES compatibility
3. **Dynamic Dockerfile**: Creates a minimal Dockerfile if not present in the
   repository
4. **Graceful failure**: Logs warnings instead of failing the workflow if push
   fails (e.g., insufficient permissions)

If Docker is unavailable or the registry is unreachable, the workflow continues
and relies solely on artifacts.

## Consumer Job

The `consume` job demonstrates how downstream systems or restricted runners can:

1. Download the `app_bundle` artifact to `/tmp/payload`
2. Install or verify the contents
3. Optionally pull the container image (if `publish` succeeded)

This job simulates installation on runners that may have limited network access
or different tool availability than the build runners.

## Configuration Variables

Override these via repository secrets or environment variables:

### Environment Variables

- `RETENTION_DAYS` (default: `30`): Artifact retention period in days
- `IMAGE_NAME` (default: `app`): Container image name component
- `GIT_LFS_SKIP_SMUDGE` (default: `1`): Skip LFS during checkout for speed

### Secrets

- `GITHUB_TOKEN`: Automatically provided by Actions; must have
  `packages: write` permission
- `REGISTRY` (optional): Override auto-detected registry endpoint

### Overriding Registry

To use a custom registry endpoint, set a repository secret named `REGISTRY`:

```yaml
env:
  REGISTRY: ${{ secrets.REGISTRY || 'ghcr.io' }}
```

Then update the `env-detect` step to use this value.

## Artifact v4 Constraints

The pipeline uses `actions/upload-artifact@v4` and
`actions/download-artifact@v4`, which have notable differences from v3:

1. **Immutable artifacts**: Once uploaded, artifacts cannot be updated; use
   unique names for versioning
2. **Retention limits**: Maximum 90 days retention on GitHub.com; check GHES
   limits
3. **Download behavior**: `download-artifact@v4` downloads to a flat directory
   by default; specify `path` explicitly
4. **Merge behavior**: Multiple artifacts with the same name are not
   automatically merged; use `merge-multiple: true` if needed

Refer to [actions/upload-artifact
docs](https://github.com/actions/upload-artifact) for the latest constraints.

## Multi-part Archives (Example)

If your `dist/` exceeds 2 GiB, split before upload:

```bash
# In build job after creating dist/
tar -czf - dist/ | split -b 1G - dist-part-
```

Then upload each part as a separate artifact:

```yaml
- name: Upload multi-part artifacts
  uses: actions/upload-artifact@v4
  with:
    name: app_bundle_part_${{ strategy.job-index }}
    path: dist-part-*
```

Recombine in the `consume` job:

```bash
cat dist-part-* | tar -xzf -
```

## OCI Image Alternative

For very large assets, push as OCI images instead of artifacts:

```bash
# Tag large model files as OCI artifact
docker build -f Dockerfile.models \
  -t ${REGISTRY}/${REPO}/models:${SHA} .
docker push ${REGISTRY}/${REPO}/models:${SHA}
```

Then pull in the `consume` job:

```bash
docker pull ${REGISTRY}/${REPO}/models:${SHA}
docker create --name temp ${REGISTRY}/${REPO}/models:${SHA}
docker cp temp:/models /opt/models
docker rm temp
```

## Troubleshooting

### Docker login fails on GHES

**Symptom**: `docker login` returns authentication errors

**Solution**:

1. Verify `GITHUB_TOKEN` has `packages: write` permission in workflow
   permissions block
2. Check GHES registry endpoint: should be `containers.<hostname>`, not
   `ghcr.io`
3. Ensure container registry is enabled on your GHES instance (admin setting)

### Artifacts not found in consume job

**Symptom**: `download-artifact@v4` fails with "artifact not found"

**Solution**:

1. Check artifact name matches between upload and download (case-sensitive)
2. Verify `build` job completed successfully before `consume` runs
3. Check retention hasn't expired (unlikely within same workflow run)

### Build too large for artifacts

**Symptom**: Upload fails with size limit error

**Solution**:

1. Use multi-part archives (see example above)
2. Switch to container image strategy for large payloads
3. Consider external storage (S3/blob) with manifest in artifact

### Wheelhouse is empty or missing wheels

**Symptom**: Offline install fails because wheelhouse has no `.whl` files

**Root cause**: This was the issue documented in PR #90 - wheelhouse had only
`manifest.json` and `requirements.txt` but no actual wheels.

**Solution**:

1. Verify the build job completes the "Build wheelhouse" step successfully
2. Check the workflow logs for errors during `pip download`
3. Ensure `poetry-plugin-export` is installed (added to CI workflow)
4. Verify the build summary shows non-zero wheel count
5. Check the consume job logs for validation errors
6. If persistent, check if `poetry.lock` is out of sync with `pyproject.toml`

The CI workflow now validates wheelhouse contents and fails if no wheels are
found, preventing this issue from occurring in CI artifacts.

### Poetry export command not found

**Symptom**: `build-wheelhouse.sh` fails with "command export does not exist"

**Solution**:

1. Install `poetry-plugin-export`: `pip install poetry-plugin-export`
2. Or use Poetry 1.x which had export built-in
3. The CI workflow now automatically installs this plugin

The build script has fallback logic to generate requirements.txt from
`poetry.lock` if export is unavailable.

### Offline install test fails in consume job

**Symptom**: Consumer job shows errors installing from wheelhouse

**Solution**:

1. Check wheel count in consume job logs - should be > 0
2. Verify requirements.txt exists in wheelhouse
3. Check for platform-specific wheel incompatibilities
4. Ensure Python version matches between build and consume
5. Check for missing dependencies that weren't captured in export

### pip-audit not available offline

**Symptom**: Security scanning fails in air-gapped environment

**Solution**:

The CI workflow now automatically includes pip-audit in the wheelhouse.
If it's missing:

1. Verify the "Build wheelhouse" step includes pip-audit download
2. Check consume job validation confirms pip-audit presence
3. Manually add: `python -m pip download --dest wheelhouse pip-audit`

### Cache not working in air-gapped GHES

**Symptom**: `actions/cache@v4` fails or is very slow

**Solution**:

1. The pipeline intentionally skips cache when not available; this is expected
2. Pre-seed runner tool cache with Python, pip packages, etc. on GHES runners
3. Use repository-local vendoring (e.g., `vendor/wheelhouse`) for dependencies

## Column Width Compliance

This pipeline YAML is formatted to stay within 120 columns for readability and
lint compliance. Comments indicating GHES-specific branches are marked clearly
with `# GHES branch:` prefixes.

## Extending the Pipeline

### Workflow Triggers

The pipeline runs automatically on:

- **Push to main branch**: Full build, publish, and consume pipeline
- **Pull requests**: Full build, publish, and consume (artifacts from PRs are
  pruned more aggressively)
- **Manual trigger**: Via Actions UI → CI → Run workflow
- **Weekly schedule**: Monday at 9:00 UTC for dependency checks

The scheduled run only executes the `dependency-check` job to avoid unnecessary
builds.

## Pipeline Extension Steps

To add new build steps:

1. Add commands in the `build` job's "Build project" step
2. Ensure outputs go to `./dist/` directory
3. Update `consume` job to handle new artifact types
4. Document changes in this README

For new language caches (pnpm, npm, etc.):

1. Add cache check step similar to "Check for pip cache"
2. Conditionally enable `actions/cache@v4` in setup steps
3. Document cache paths and invalidation strategy

### Adding Dependencies to Wheelhouse

To add new dependencies to the offline wheelhouse:

1. Add the dependency to `pyproject.toml` under appropriate section
   (dependencies, extras, or dev-dependencies)
2. Run `poetry lock` to update `poetry.lock`
3. Commit changes - CI will automatically rebuild wheelhouse
4. The wheelhouse generation in CI includes all extras and dev dependencies

To add system tools (like pip-audit) to wheelhouse:

1. Edit `.github/workflows/ci.yml` build job
2. Add `python -m pip download --dest dist/wheelhouse <package>` command
3. Update requirements.txt if needed
4. Test locally with `bash scripts/build-wheelhouse.sh`

### Validating Offline Packages

The `consume` job validates that:

- Wheelhouse contains actual wheel files (not just manifest)
- Offline installation works without internet
- Required security tools (pip-audit) are available
- Package structure is correct for air-gapped deployment

This prevents issues like PR #90 where wheelhouse had metadata but no wheels.

**Manual validation checklist**:

1. Download `app_bundle` artifact from Actions tab
2. Extract and verify structure:

   ```bash
   unzip app_bundle.zip
   find dist/wheelhouse/platforms -maxdepth 2 -name "*.whl" | sort
   wc -l < dist/wheelhouse/requirements.txt  # Should show package count
   cat dist/wheelhouse/multi_platform_manifest.json  # Aggregated manifest
   ls -1 dist/wheelhouse/archives  # Per-platform tarballs
   ```

3. Test offline install:

   ```bash
   python -m venv test-venv
   source test-venv/bin/activate
   python -m pip install --no-index \
     --find-links dist/wheelhouse \
     -r dist/wheelhouse/requirements.txt
   pip-audit --version  # Should work if pip-audit included
   deactivate
   ```

4. Check BUILD_INFO for metadata:

   ```bash
   cat dist/BUILD_INFO
   # Should show build timestamp and git SHA
   ```

**Automated validation**:

The consume job automatically validates these steps and fails if:

- No wheels found in wheelhouse (wheel_count == 0)
- Offline install fails
- Required files missing (requirements.txt, manifest.json/multi_platform_manifest.json)

Check the workflow summary for build statistics including wheel count and
wheelhouse size.

## Composite Actions

The CI workflow now uses standardized composite actions to reduce duplication
and ensure consistency across all workflows:

### `setup-python-poetry`

Located in `.github/actions/setup-python-poetry/`, this action standardizes
Python and Poetry installation:

- **Inputs**: `python-version` (default: 3.12), `poetry-version` (default: 1.8.3),
  `cache-pip`, `install-poetry-export`
- **Outputs**: `python-version`, `poetry-version`
- **Usage**: Ensures consistent Poetry 1.8.3 across all workflows
- **Benefits**: Single source of truth for Python/Poetry setup

### `build-wheelhouse`

Located in `.github/actions/build-wheelhouse/`, this action encapsulates
wheelhouse building logic:

- **Inputs**: `output-dir`, `extras`, `include-dev`, `include-pip-audit`,
  `create-archive`, `validate`
- **Outputs**: `wheelhouse-path`, `wheel-count`
- **Features**: Calls `scripts/build-wheelhouse.sh`, generates manifests,
  runs offline_doctor.py validation
- **Benefits**: Consistent wheelhouse building across CI, preflight, and
  offline-packaging workflows

### `verify-artifacts`

Located in `.github/actions/verify-artifacts/`, this action standardizes
artifact verification:

- **Inputs**: `artifact-dir`, `run-offline-doctor`, `run-verify-script`,
  `fail-on-warnings`
- **Outputs**: `validation-status` (pass/warn/fail)
- **Features**: Runs offline_doctor.py and verify_artifacts.sh, generates
  comprehensive summary
- **Benefits**: Consistent validation with configurable failure modes

See [docs/workflow-orchestration.md](../docs/workflow-orchestration.md) for
detailed information on how these actions coordinate across workflows.

## References

- [GitHub Actions
  documentation](https://docs.github.com/en/actions)
- [GHES Actions
  docs](https://docs.github.com/en/enterprise-server@latest/admin/github-actions)
- [Container registry
  auth](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Artifact v4 migration
  guide](https://github.com/actions/upload-artifact/blob/main/docs/MIGRATION.md)
- [Workflow Orchestration Guide](../docs/workflow-orchestration.md)
