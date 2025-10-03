# Dependency Upgrade TODOs

Updated: 2025-10-03

This manifest highlights outstanding work to bring the dependency upgrade
architecture to full parity with the roadmap. Update it whenever new tasks are
identified or items land in `main`.

## How to read this list

- **Status** captures delivery state (`in progress`, `planned`, `blocked`).
- **Owner** names the accountable group; adjust as teams shift.
- **Notes** provide quick context, escalation triggers, or links to tickets.

## Backlog (near term)

### Snapshot lifecycle automation

- **Status:** in progress
- **Owner:** platform-automation
- **Notes:** Guard writes manifests, index entries, prunes retention, and the
  `prometheus deps snapshot ensure` command provisions the Temporal schedule.
  Follow-up work: wire nightly CI guard runs, add Temporal cron jobs for
  snapshot refresh plus notifications, and document the operator runbook.

### Observability instrumentation

- **Status:** in progress
- **Owner:** observability guild
- **Notes:** Guard, planner, and the `prometheus deps status` CLI now emit
  spans/metrics. Follow-up work: adopt the telemetry helper across remaining
  dependency CLI subcommands and extend dashboards to visualise the new
  metrics.

### Mirror signature regression tests

- **Status:** completed
- **Owner:** qa-foundation
- **Notes:** Regression tests now cover unsigned, mismatched, and refreshed
  artefacts in `tests/unit/scripts/test_mirror_manager.py`. Follow-up: add a
  CLI-level check to confirm non-zero exits when signatures fail.

### Schedule payload normalization tests

- **Status:** planned
- **Owner:** platform-automation
- **Notes:** Extend `tests/unit/test_dependency_snapshot_workflow.py` with
  additional payload permutations (invalid enums, mixed-case booleans) and note
  operator-facing error handling expectations.

## Backlog (longer term)

### Model registry governance

- **Status:** planned
- **Owner:** model-platform
- **Notes:** Validate model registry cadence and signature requirements inside
  `scripts/download_models.py`, producing actionable reports for operators.

### Guided operator remediation prompts

- **Status:** planned
- **Owner:** dependency-governance squad
- **Notes:** Design interactive prompts for `prometheus deps` commands so
  non-technical operators receive step-by-step remediation when guard severity
  crosses policy thresholds.

## Recently completed

- Documented dependency upgrade progress tracking in
  `docs/dependency-upgrade-architecture.md`.
- Captured outstanding items and owners in this manifest for shared visibility.
- Delivered weighted autoresolver scoring plus
  `prometheus deps upgrade --plan auto` with optional command execution,
  scoreboard output, and SBOM-relative defaults for command execution.
- Shipped mirror management CLI (`prometheus deps mirror --status|--update`)
  with signature verification for wheel/model mirrors.
- Guard now enforces signature requirements, handles snooze expiry, and emits
  telemetry; unit tests cover the new behavior.
- Temporal dependency snapshot scheduling exposed via
  `prometheus deps snapshot ensure`, keeping CLI orchestration aligned with the
  Temporal workflow.
- Snapshot schedule request coercion normalized planner package overrides and
  boolean flags, with unit tests documenting the behavior.
