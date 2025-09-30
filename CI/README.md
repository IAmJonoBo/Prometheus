# CI Pipeline Documentation

This document explains the dual-environment CI pipeline that works on both
GitHub.com and GitHub Enterprise Server (GHES) in air-gapped deployments.

## Overview

The CI pipeline automatically detects its environment via `$GITHUB_SERVER_URL`
and adapts its behavior for registry endpoints, artifact handling, and caching
strategies. It consists of three main jobs:

1. **build** – Checkout, build, and upload artifacts
2. **publish** – Build and push container images (conditional on Docker
   availability)
3. **consume** – Download artifacts and demonstrate installation (simulates
   restricted runners)

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
- **Contents**: All files from `./dist/` directory

### Large Payloads (>2 GiB)

If your build produces artifacts exceeding ~2 GiB, consider:

1. **Multi-part archives**: Split large files before upload using `split`
   command
2. **Container images**: Push large assets as OCI images instead (handled by
   `publish` job)
3. **External storage**: Use S3/blob storage with signed URLs and store only
   the manifest in artifacts

The current implementation prioritizes artifacts for smaller payloads and
container images for long-lived or large assets.

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

Language-aware caching (pip) is conditional:

- **Enabled**: If `pip cache info` succeeds and `pyproject.toml` exists
- **Disabled**: If no local cache or air-gapped environment without cache
  seeding

This prevents internet pulls in restricted environments.

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

To add new build steps:

1. Add commands in the `build` job's "Build project" step
2. Ensure outputs go to `./dist/` directory
3. Update `consume` job to handle new artifact types
4. Document changes in this README

For new language caches (pnpm, npm, etc.):

1. Add cache check step similar to "Check for pip cache"
2. Conditionally enable `actions/cache@v4` in setup steps
3. Document cache paths and invalidation strategy

## References

- [GitHub Actions
  documentation](https://docs.github.com/en/actions)
- [GHES Actions
  docs](https://docs.github.com/en/enterprise-server@latest/admin/github-actions)
- [Container registry
  auth](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Artifact v4 migration
  guide](https://github.com/actions/upload-artifact/blob/main/docs/MIGRATION.md)
