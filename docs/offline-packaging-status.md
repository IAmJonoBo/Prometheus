# Offline packaging status board

This board captures the most recent dependency telemetry emitted by the offline
packaging orchestrator. Pair it with the run manifest at
`vendor/packaging-run.json` to trace when artefacts were last refreshed.

## How to refresh the data

1. Run the dependency phase:

   ```bash
   poetry run python scripts/offline_package.py --only-phase dependencies
   ```

2. Review the WARN/INFO lines for a quick heads-up on major or minor updates.
3. Inspect `vendor/wheelhouse/outdated-packages.json` for the structured report.

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

Keep this document alongside the latest packaging artefacts so stakeholders can
see drift at a glance and track remediation progress.
