# Offline packaging orchestrator

The offline packaging orchestrator turns a messy release checklist into a
predictable, idempotent command. It prepares dependency wheels, model caches,
container archives, and git metadata while producing a manifest that auditors
and CI pipelines can inspect.

## Why it exists

- Guard against Python, pip, and Poetry drift that previously broke builds.
- Keep `vendor/` assets up to date with one repeatable command.
- Reduce manual git clean-up by staging, committing, and optionally pushing
  refreshed artefacts.
- Emit machine-readable telemetry so automation can promote artefacts safely.

## Workflow phases

Each run executes the following phases (use `--only-phase` or `--skip-phase`
to customise the order):

1. **cleanup** removes stale artefacts, ensures `git-lfs` hooks are installed,
   repairs misconfigured hooks, replaces vendor symlinks with on-disk files,
   purges Finder metadata such as `.DS_Store` and AppleDouble records, applies
   optional `git lfs checkout`, honours preserved globs while tidying the
   repository, and when configured will audit the wheelhouse to delete orphan
   dependency artefacts before rebuilding.
2. **environment** checks Python, pip, Poetry, Docker, and optional helpers
   such as `uv`, installing or upgrading tools when configured to do so.
3. **dependencies** refreshes the wheelhouse via
   `scripts/build-wheelhouse.sh`, respecting configured extras and dev
   dependencies, and records an audit of missing or orphan dependency wheels
   for telemetry and doctor reports.
4. **models** downloads Hugging Face, sentence-transformer, and spaCy assets
   into `vendor/models/` and records a manifest of fetched artefacts.
5. **containers** exports requested container images to `.tar` archives,
   ready for import on offline hosts.
6. **archive** compresses the refreshed wheelhouse into `wheelhouse.tar.gz`
   and writes a companion checksum so CI and human operators can download a
   single bundle instead of thousands of individual wheels.
7. **checksums** writes `vendor/CHECKSUMS.sha256` so downstream operators can
   validate content integrity.
8. **git** updates `.gitattributes`, verifies tracked LFS artefacts are
   materialised, stages changed paths, and optionally commits and pushes the
   refreshed assets.

## Configuration quick reference

Default knobs live in `configs/defaults/offline_package.toml` and map directly
to dataclasses inside `prometheus/packaging/offline.py`.

- `[poetry]` now supports `min_version`, `auto_install`, and `self_update` so
  the orchestrator can install Poetry on demand or ensure it meets a minimum
  version before the wheelhouse phase runs. The default configuration now pins
  Poetry to `>=2.2.0` and enables both toggles so runners automatically install
  and upgrade Poetry when required. Supply `EXTRAS` (for example,
  `rag,llm,governance`) when invoking the orchestrator to pre-build wheelhouses
  for retrieval, model, or policy workstreams.
- `[cleanup]` controls which vendor directories reset, which paths are
  deleted outright, and which globs should survive a reset.
  `ensure_lfs_hooks` installs `git-lfs` hooks locally when required,
  `repair_lfs_hooks` rewrites trunk-managed hook scripts to invoke the
  matching `git lfs` subcommand,
  `normalize_symlinks` rewrites fragile vendor symlinks to plain files,
  `metadata_directories` and `metadata_patterns` strip macOS cruft across key
  vendor paths, `remove_orphan_wheels` deletes dependency artefacts that no
  longer appear in `requirements.txt`, and `lfs_paths` guarantees git-lfs
  pointers are hydrated before packaging begins.
- `[git]` introduces precise staging lists, templated commit messages, optional
  sign-off, and guarded pushes. The orchestrator ensures the listed patterns
  exist in `.gitattributes` to keep large files tracked by git-lfs and uses
  `pointer_check_paths` to refuse commits when LFS pointers remain unhydrated.
- `[telemetry]` can emit `vendor/packaging-run.json`, recording start and end
  timestamps, per-phase outcomes, and the config file that guided the run.
- `[commands]` adds resilient shell execution by allowing configurable retry
  counts and a linear back-off between attempts.
- GitHub Actions workflow (`.github/workflows/offline-packaging.yml`)
  refreshes the wheelhouse weekly and on demand. It uses
  `python -m build --wheel` to generate the project’s pure-Python wheel across
  Linux, macOS, and Windows, then uploads both the raw directory and the
  compressed archive so air-gapped environments can pick up the latest builds.
  When the workflow runs, the final step deletes older
  `offline-packaging-suite` artefacts via the Actions API using the job’s
  `GITHUB_TOKEN`, keeping only the most recent three runs in GitHub storage.
  The workflow now installs Git LFS tooling up front, resets the runner
  workspace via a Python cleanup guard before checkout, enables
  `actions/checkout`’s `clean` mode alongside `lfs: true`, hydrates Git LFS
  pointers explicitly, verifies them via `scripts/ci/verify-lfs.sh`, and runs
  `git clean -fdx` so cached or untracked files cannot block subsequent clones
  or checkouts.

## Git automation

When `git.commit` is enabled the orchestrator stages the configured paths,
renders the commit message with `{timestamp}` and `{branch}` tokens, and
optionally appends `--signoff`. If `git.push` is also true the refreshed
artefacts are pushed to the target remote after confirming the working tree is
clean. Dry runs log the intended operations without mutating the repository.

## Telemetry and manifests

Successful runs populate three per-phase manifests under `vendor/` plus an
optional `packaging-run.json` summary. These artefacts describe the commit
hash, dependencies, models, containers, wheelhouse audit results, repository
hygiene counters, and timing data so CI workflows or auditors can reason about
the run without rerunning the tool.

The `repository_hygiene` block lists how many symlinks were rewritten, which
LFS paths were verified, the detected hooks directory, and which hook files
were repaired, aligning telemetry with the CLI log lines emitted after every
execution.

## Command retries

Shell commands executed by the orchestrator respect the `[commands]` settings.
Failures trigger warnings and, when retries remain, wait for the configured
back-off before trying again. Once the attempt budget is exhausted the final
error is raised, ensuring failures surface promptly without hiding flaky
systems.

## Usage tips

- Always start with `--dry-run` after editing configuration to confirm the
  planned actions.
- Use `git.ensure_branch` when refreshing artefacts on a dedicated branch for
  release validation.
- Combine with `scripts/cleanup-macos-cruft.sh` on macOS hosts to avoid Finder
  metadata sneaking into checksum results.
- Run `scripts/offline_doctor.py` before packaging to verify Python, pip,
  Poetry, Docker, and wheelhouse readiness without mutating the repository.
- Run `scripts/ci/verify-lfs.sh` to confirm that all Git LFS pointers are
  hydrated before invoking the orchestrator (the script attempts a fix and
  fails fast if artefacts remain missing).
