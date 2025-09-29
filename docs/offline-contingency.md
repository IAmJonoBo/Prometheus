# Offline packaging contingency

Prometheus relies on Git LFS to distribute large wheelhouse, model, and
container artefacts. When LFS is briefly unavailable (for example, during
GitHub incidents or when a runner clones with `GIT_LFS_SKIP_SMUDGE=1`), the
repository can still boot by pulling the tarballs uploaded by the offline
packaging workflow. This playbook documents the fallback procedure so Copilot
workspaces, GitHub Actions reruns, and other remote environments stay
productive.

## Quick checklist

1. Clone with LFS smudge disabled when the remote repository is known to be
   missing objects:

   ```bash
   export GIT_LFS_SKIP_SMUDGE=1
   git clone https://github.com/IAmJonoBo/Prometheus.git
   cd Prometheus
   git lfs install --skip-smudge
   ```

2. Fetch the latest artefact bundle produced by the `Offline Packaging`
   workflow.
3. Run `scripts/bootstrap_offline.py` with the downloaded tarballs so pip and
   Poetry install from the hydrated directories.

## Fetching workflow artefacts

Every workflow run uploads four archives:

- `wheelhouse.tar.gz` (Python wheels + requirements)
- `models.tar.gz` (vendor models cache)
- `images.tar.gz` (container image exports)
- `offline-packaging-suite` (Actions artefact containing the above plus
  manifests and checksums)

From a machine with access to GitHub, download the most recent artefacts. The
GitHub CLI can retrieve them directly:

```bash
# List the latest offline-packaging runs
gh run list --workflow "Offline Packaging" --limit 5

# Download wheelhouse/models/images archives from the newest successful run
RUN_ID=$(gh run list --workflow "Offline Packaging" --json databaseId,status \
  --jq 'map(select(.status=="completed"))[0].databaseId')

gh run download "$RUN_ID" \
  --name offline-packaging-suite \
  --repo IAmJonoBo/Prometheus \
  --dir ./offline-suite
```

The tarballs include the directory names expected by the repository (for
example, extracting `wheelhouse.tar.gz` under `vendor/` recreates
`vendor/wheelhouse`).

## Bootstrapping with tarballs

The updated bootstrap helper downloads missing artefacts automatically when
URLs are supplied. If you already have the tarballs locally, point the script at
their `file://` URIs. Otherwise, provide the signed download URLs from the
workflow run alongside a token that can access GitHub artefacts (for example,
`GITHUB_TOKEN`).

```bash
export GITHUB_TOKEN=<token-with-actions-scope>
python scripts/bootstrap_offline.py \
  --wheelhouse-url "file://$(pwd)/offline-suite/wheelhouse.tar.gz" \
  --models-url "file://$(pwd)/offline-suite/models.tar.gz" \
  --images-url "file://$(pwd)/offline-suite/images.tar.gz"
```

Use the `--force-download-*` switches when you want to replace existing
contents (useful after clearing stale LFS pointers).

## Troubleshooting

- **Wheelhouse directory still empty** – verify the archive contains a
  `wheelhouse/` folder by running `tar -tzf wheelhouse.tar.gz | head`. The
  bootstrap helper expects that directory name when extracting.
- **Unauthorised downloads** – ensure the token referenced by
  `--artifact-token-env` (defaults to `GITHUB_TOKEN`) has `actions:read`
  permissions. Copilot workspaces expose this token automatically.
- **Residual LFS pointers** – run `scripts/cleanup-macos-cruft.sh --include-git`
  to remove macOS AppleDouble files and then re-run `git lfs fetch --all`
  followed by the bootstrap script.

Following this playbook keeps remote environments productive even when Git LFS
objects are temporarily unavailable.
