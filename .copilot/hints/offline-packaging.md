# Offline packaging quick reference

Use this cheat sheet when nudging Copilot or teammates to refresh offline
artefacts.

## Targeted dependency refresh

- Run the dependency phase only to avoid long container/model steps:
  `poetry run python scripts/offline_package.py --only-phase dependencies`
- To skip heavy wheel downloads while still collecting update telemetry, wrap
  the orchestrator and override `_run_command` for `build wheelhouse` as shown
  in `tests/unit/packaging/test_offline.py::test_dependency_update_check_writes_report`.
- Update reports land in `vendor/wheelhouse/outdated-packages.json`; the run
  manifest is in `vendor/packaging-run.json`.

## Acting on update summaries

- Check the `summary` block for `counts` and `next_actions`. Major updates are
  also logged as WARN level entries during the CLI run.
- Align follow-up work with the recommended actions embedded per dependency in
  the `updates` array.
- The run manifest now records `auto_update_policy`, and the CLI prints the
  effective settings each run—use both to confirm which knobs were active.

## Smart defaults

- Configuration lives in `configs/defaults/offline_package.toml`; tweak the
  `[updates]` section to change auto-apply or inclusion rules.
- Turn on `[updates.auto]` to enable unattended upgrades: raise
  `max_update_type` when you want to allow minor or major bumps and use the
  `allow`/`deny` lists or `max_batch` limiter to scope which packages move.
- Prefer CLI overrides when experimenting: add `--auto-update` (plus
  `--auto-update-max`, `--auto-update-allow`, `--auto-update-deny`, or
  `--auto-update-batch`) to a one-off run instead of editing config.

## LFS & workspace hygiene

- Confirm `git-lfs` is present: `git lfs version`
- Hydrate pointers before running the orchestrator:
  - `git lfs install --local`
  - `git lfs fetch --all && git lfs checkout` (fallback: `git lfs pull`)
  - `bash scripts/ci/verify-lfs.sh` fails fast if any pointers remain
- Keep the tree pristine for repeatable runs:
  `git reset --hard HEAD && git clean -fdx`
- In CI, run `actions/checkout` with `clean: true`, `fetch-depth: 0`, and set
  `GIT_LFS_SKIP_SMUDGE=1` so hydration happens explicitly in a controlled step.

Keep this guide handy so Copilot can propose consistent responses whenever the
packaging workflow needs to run in constrained environments.
