# Offline packaging status board

This board captures the most recent dependency telemetry emitted by the offline
packaging orchestrator. Pair it with the run manifest at
`vendor/packaging-run.json` to trace when artefacts were last refreshed and
to review repository hygiene counters (symlink replacements, LFS
verification paths, and hook repairs) for each run.

## How to refresh the data

1. (Optional) Run the preflight doctor to confirm tooling and wheelhouse
   readiness without mutating the repo:

```bash
poetry run python scripts/offline_doctor.py --format table
```

1. Run the dependency phase to refresh manifests and drift telemetry:

   ```bash
   poetry run python scripts/offline_package.py --only-phase dependencies
   ```

1. Review the WARN/INFO lines for dependency updates and the
   `wheelhouse_audit` summary (missing wheels, orphan artefacts, and any
   items pruned when `[cleanup.remove_orphan_wheels]` is enabled).
1. Inspect `vendor/packaging-run.json` for the persisted telemetry (`updates`
   and `wheelhouse_audit` blocks mirror the CLI output).
1. Inspect `vendor/wheelhouse/outdated-packages.json` for the structured
   package report.

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
- The `Offline Packaging` GitHub workflow runs weekly (or on demand). It relies
  on `python -m build --wheel` to generate the pure-Python project wheel
  (`py3-none-any`) on Linux, macOS, and Windows runners, then executes the
  packaging orchestrator with the full extras set (`pii`, `observability`,
  `rag`, `llm`, `governance`, `integrations`). Each run publishes the refreshed
  wheelhouse directory, a compressed `wheelhouse.tar.gz` bundle, manifests, and
  dependency reports so air-gapped mirrors can ingest the latest artefacts with
  minimal manual work.
- When the optional `ARTIFACT_CLEANUP_TOKEN` secret is configured in the
  workflow, older `offline-packaging-suite` artefacts are pruned via the GitHub
  Actions API so that only the latest three runs remain; without the secret the
  pruning step is skipped automatically.

Keep this document alongside the latest packaging artefacts so stakeholders can
see drift at a glance and track remediation progress.
