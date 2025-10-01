# Offline packaging status board

This board captures the most recent dependency telemetry emitted by the offline
packaging orchestrator. Pair it with the run manifest at
`vendor/packaging-run.json` to trace when artefacts were last refreshed and
to review repository hygiene counters (symlink replacements, LFS
verification paths, and hook repairs) for each run.

## How to refresh the data

1. Run the dependency preflight guard to verify PyPI still exposes binary
   wheels for every supported runtime combination:

   ```bash
   python scripts/preflight_deps.py
   ```

   Add `--json` to capture a machine-readable summary, or pass
   `--packages <name>` when you need to isolate a small set of upgrades. If a
   package legitimately ships sdists only, supply `ALLOW_SDIST_FOR="pkg1,pkg2"`
   when rerunning `scripts/manage-deps.sh` so the guard treats it as a warning.

1. (Optional) Run the offline doctor to confirm tooling and wheelhouse
   readiness without mutating the repo:

   ```bash
   poetry run python scripts/offline_doctor.py --format table
   ```

1. Run the dependency phase to refresh manifests, constraints, and drift
   telemetry:

   ```bash
   poetry run python scripts/offline_package.py --only-phase dependencies
   ```

1. Review the WARN/INFO lines for dependency updates and the
   `wheelhouse_audit` summary (missing wheels, orphan artefacts, and any
   items pruned when `[cleanup.remove_orphan_wheels]` is enabled).
1. Inspect `vendor/packaging-run.json` for the persisted telemetry (`updates`
   and `wheelhouse_audit` blocks mirror the CLI output).
1. Inspect `vendor/wheelhouse/outdated-packages.json` for the structured
   package report and `constraints/production.txt` for the pip constraints
   exported during the refresh.

## Report anatomy

- `updates`: package-by-package view including `update_type` and
  `recommended_action`.
- `summary.counts`: severity buckets (major, minor, patch, unknown).
- `summary.next_actions`: curated follow-up tasks drawn from the current run.
- `summary.primary_recommendation`: the single headline to share with the team.

## Operational guidance

- Prioritise items flagged as `major` before the next release train.
- When only patches remain, schedule them alongside the next routine refresh.
- If the summary indicates a failure, re-run the command with `--verbose` and
  capture logs for the enablement team.
- Treat a `wheelhouse_audit.status` of `attention` as a blocker for air-gapped
  deployment until missing wheels or orphan artefacts are resolved.

## Current dependency blockers

- `cryptography` must remain `<44.1` until the `presidio-anonymizer` and
  `presidio-analyzer` packages relax their upper bound.
- `lxml` is capped at `<6` by `htmldate`; upgrading would require a new
  htmldate release or an alternative HTML dating strategy.
- `thinc` ≥9.x is incompatible with the currently pinned `spacy` line; moving
  forward entails a coordinated upgrade of the NLP stack.
- `pydantic-core` tracks the version shipped with `pydantic 2.11.9`, which is
  the latest release on PyPI at the time of writing.
- `argon2-cffi` now ships with the core dependency set but we intentionally
  hold it on the 23.x line (with `argon2-cffi-bindings` on the 21.x line) to
  retain manylinux2014-compatible wheels. The upstream 25.x series only
  publishes glibc 2.26+ builds, so we will revisit this once the maintainers
  ship cp311 manylinux2014 artefacts or our baseline glibc requirement
  increases.
- `llama-cpp-python` is constrained to Python `<3.12` via extras markers until
  upstream publishes cp312 manylinux2014 wheels, keeping wheelhouse builds
  binary-only without dropping the `llm` bundle.

## Automated remediation

- Enable `[updates.auto]` in `configs/defaults/offline_package.toml` to let the
  orchestrator apply low-risk updates (patch by default) without manual
  intervention.
- Review the `summary.auto_applied` array or the CLI log line to confirm which
  packages were touched and run smoke tests as needed.
- For ad-hoc tuning, pass CLI overrides such as `--auto-update-max minor`
  or `--auto-update-allow <pkg>`; they activate automatic upgrades for that
  run without editing the shared config.
- The manifests and `outdated-packages.json` include an `auto_update_policy`
  block capturing the exact settings used for the run, complementing the CLI
  log line for audit trails.
- Wheelhouse clean-up honours `[cleanup.remove_orphan_wheels]` and the doctor
  output; enable the flag when running unattended so stale wheels do not mask
  missing dependency builds.
- The `Offline Packaging` GitHub workflow runs weekly (or on demand). It
  relies on `python -m build --wheel` to generate the pure-Python project
  wheel (`py3-none-any`) on Linux, macOS, and Windows runners, then executes
  the packaging orchestrator with the full extras set (`pii`, `observability`,
  `rag`, `llm`, `governance`, `integrations`). Each run publishes the
  refreshed wheelhouse directory, a compressed `wheelhouse.tar.gz` bundle,
  manifests, and dependency reports so air-gapped mirrors can ingest the
  latest artefacts with minimal manual work. The job now installs Git LFS
  tooling, wipes the runner workspace via a Python cleanup guard prior to
  checkout, enables pristine checkouts via `actions/checkout`’s `clean` flag
  and `lfs: true`, hydrates Git LFS pointers, verifies them with
  `scripts/ci/verify-lfs.sh`, and runs `git clean -fdx` so no stale or
  untracked files interfere with later fetches.
- The workflow prunes older `offline-packaging-suite` artefacts through the
  GitHub Actions API using the job’s `GITHUB_TOKEN`, retaining only the most
  recent three runs.

## Forward-looking watchlist

- Monitor upstream release notes for the `argon2` stack so we can lift the
  temporary pin once binary wheels for glibc 2.17/2014 are restored.
- Keep an eye on `numpy` musllinux/ARM wheels—if they slip behind CPython
  releases, add them to the wheelhouse allowlist on a temporary basis and
  file upstream bugs.
- Add a recurring Renovate task to diff `platform_manifest.json` against the
  expected extras list; deviations usually indicate the MBOM changed outside
  of lockfile updates.
- Prepare a fallback path for `pip-audit` outages (mirrored wheel or internal
  proxy) so the security tooling step does not block emergency packaging runs.

Keep this document alongside the latest packaging artefacts so stakeholders can
see drift at a glance and track remediation progress.
