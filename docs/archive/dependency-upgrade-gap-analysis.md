# Dependency Upgrade Gap Analysis

Updated: 2025-10-03

This note captures the current alignment between the documented roadmap for the
dependency upgrade system and what is implemented in the repository. It
compares `docs/dependency-governance.md`,
`docs/dependency-upgrade-todos.md`, and the live code/tests.

## Mirror management CLI & signature verification

- **Documentation:** Now marked as shipped in the architecture and todo docs.
- **Reality:** `prometheus deps mirror --status/--update` commands ship today and
  enforce signatures through `scripts/mirror_manager.py`. Unit tests now
  exercise verification paths for unsigned, mismatched, and signed artifacts.
- **Evidence:** `prometheus/cli.py` (mirror commands);
  `scripts/mirror_manager.py` (signature validation);
  `tests/unit/scripts/test_mirror_manager.py` (signature regression tests).
- **Gap:** Consider a high-level CLI test to ensure Typer exits non-zero when
  signatures fail and report outcomes to operators.

## Snapshot lifecycle automation

- **Documentation:** Notes the `prometheus deps snapshot ensure` command and
  retains backlog items for Temporal/CI scheduling hooks.
- **Reality:** Guard persists manifests, writes
  `var/upgrade-guard/index/*.json`, and prunes retention. The new CLI command
  provisions the Temporal schedule, yet nightly CI cadence and automated
  notifications are still missing.
- **Evidence:** `scripts/upgrade_guard.py` (`_write_snapshot_index`,
  `_prune_snapshot_retention`); `prometheus/cli.py` (snapshot ensure command);
  `.github/workflows/dependency-preflight.yml` (no schedule block).
- **Gap:** Finish CI schedule wiring, add Temporal cron notifications, and
  document the operational runbook.

## Signature enforcement & snooze expiry

- **Documentation:** Reflects delivered status in the architecture doc.
- **Reality:** Guard enforces signature policy and snooze expiry, influencing
  risk and exit codes, with dedicated tests.
- **Evidence:** `scripts/upgrade_guard.py` (`_assess_signature_compliance`,
  `_assess_snoozes`, `_apply_contract_enforcements`);
  `tests/unit/scripts/test_upgrade_guard.py` (signature and snooze cases).
- **Gap:** Evaluate whether the upgrade planner requires equivalent
  signature/snooze enforcement or explicit documentation.

## Observability instrumentation

- **Documentation:** Marks guard instrumentation as shipped while noting CLI and
  planner gaps.
- **Reality:** Guard, planner, and the `prometheus deps status` CLI command now
  emit spans and Prometheus metrics. Dashboards have not yet been extended and
  other dependency CLI subcommands still need to adopt the shared telemetry
  wrapper.
- **Evidence:** `scripts/upgrade_guard.py` (`TRACER`, `GUARD_RUN_COUNTER`);
  `scripts/upgrade_planner.py` (`PLANNER_STAGE_DURATION`, span duration
  attributes); `prometheus/cli.py` (`_dependency_command_span`,
  `DEPS_COMMAND_COUNTER`).
- **Gap:** Extend dashboards to visualise the new metrics and ensure remaining
  dependency CLI subcommands use the telemetry helper.

## Contract & policy extensions

- **Documentation:** Reclassified as shipped.
- **Reality:** Contract already includes signatures, snoozes, environment
  alignment, and guard surfaces them in reports.
- **Evidence:** `configs/dependency-profile.toml`;
  `scripts/upgrade_guard.py` (`_evaluate_contract_metadata`).
- **Gap:** Ensure downstream serializers and SDKs surface the new metadata
  fields consistently.

## Testing & automation

- **Documentation:** Updated to show current unit coverage.
- **Reality:** Unit coverage exists for signature/snooze flows and snapshot
  hygiene.
- **Evidence:** `tests/unit/scripts/test_upgrade_guard.py`.
- **Gap:** Close remaining automation gaps (mirror regression tests,
  end-to-end coverage).

## CLI & pipeline exposure

- **Documentation:** Describes the shipped CLI (including `deps snapshot ensure`)
  and flags remaining pipeline automation work.
- **Reality:** CLI exposes mirror management, guard toggles, and the snapshot
  ensure helper. The dependency preflight workflow invokes guard but still
  lacks the new scheduling flags.
- **Evidence:** `prometheus/cli.py`;
  `.github/workflows/dependency-preflight.yml`.
- **Gap:** Wire new flags into CI, add schedule management jobs, and extend
  operator guidance.

## Schedule payload normalization

- **Documentation:** Highlights the request coercion helpers that normalize
  planner package lists and boolean flags for Temporal snapshots.
- **Reality:** `_coerce_snapshot_request` delegates to `_normalize_planner_packages`
  and `_normalize_bool_fields`, ensuring string inputs such as "0" resolve to
  `False` before Temporal receives them.
- **Evidence:** `execution/workflows.py` (normalization helpers);
  `tests/unit/test_dependency_snapshot_workflow.py` (coverage for coercion).
- **Gap:** Extend tests to cover additional payload permutations (invalid enums,
  mixed-case booleans) and document error handling for operators.

## Model registry governance

- **Documentation:** Planned.
- **Reality:** `scripts/download_models.py` does not yet validate signatures or
  cadence.
- **Evidence:** Script inspection.
- **Gap:** Keep backlog item untouched.

## Guided operator remediation prompts

- **Documentation:** Planned.
- **Reality:** No implementation yet across CLI commands.
- **Evidence:** CLI inspection.
- **Gap:** Backlog item remains.

## Summary

- Documentation now reflects the shipped mirror CLI, signature enforcement, and
  contract metadata while spotlighting outstanding automation tasks.
- Remaining gaps cluster around operational automation (scheduled runs,
  Temporal cron hooks), dashboard visualisations for new telemetry, broader
  richer test suites, and operator experience (guided prompts, model registry
  governance).
- Recommended immediate actions:
  1. Wire new scheduling knobs into CI, including `deps snapshot ensure` where
     appropriate.
  2. Expand regression tests for mirror signature verification, snapshot index
     pruning, and additional schedule payload variants.
  3. Extend Grafana (or equivalent) dashboards to surface planner/CLI telemetry
     and document operator runbooks for schedule management and error recovery.
