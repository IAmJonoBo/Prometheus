# Dependency Governance & Packaging Handbook

> Updated: 2025-10-04

## Purpose

This handbook unifies the dependency management, upgrade governance, and
packaging documentation into a single reference. It explains how policy
profiles, guard analysis, upgrade planning, packaging automation, and
air-gapped hydration collaborate so every environment stays compliant and
recoverable.

## System architecture overview

- **Policy, contracts, and telemetry** — `configs/dependency-profile.toml`,
  SBOM exports in `var/dependency-sync/`, and metadata indexes in
  `var/upgrade-guard/index/` define the desired state and evidence trail.
- **Guard & drift analysis** — `scripts/upgrade_guard.py` and
  `scripts/dependency_drift.py` merge SBOMs, CVE feeds, Renovate data, and
  contract rules to calculate severity (`safe`, `needs-review`, `blocked`).
- **Planner & autoresolver** — `scripts/upgrade_planner.py` and
  `prometheus deps upgrade` weigh candidate updates, run Poetry dry-runs,
  and emit executable command plans.
- **Scheduling & notifications** — Temporal schedules plus GitHub workflows
  (`dependency-preflight`, `dependency-contract-check`,
  `offline-packaging-optimized`) keep guard runs, packaging, and snapshots in
  sync across environments.
- **Packaging & mirroring** — `scripts/offline_package.py`,
  `scripts/mirror_manager.py`, and `scripts/manage-deps.sh` build wheelhouses,
  publish manifests, and prune stale artefacts.
- **Air-gapped hydration** — `scripts/bootstrap_offline.py` and
  `scripts/offline_doctor.py` validate and hydrate isolated runners using the
  mirrored bundles.
- **Governance & observability** — Guard snapshots, Prometheus metrics,
  OpenTelemetry spans, and reports in `governance/` provide audit evidence and
  operational visibility.

## Operational pipeline

1. **Contract synchronisation** — Run `prometheus deps sync` to align manifests
   with the policy profile before packaging or air-gapped refreshes.
2. **Preflight validation** — Execute `prometheus deps preflight` to confirm
   wheel availability across required platforms and Python versions.
3. **Guard assessment** — Invoke `prometheus deps guard` (or `prometheus deps
status`) to aggregate risk signals and enforce severity thresholds in CI.
4. **Drift analysis (optional)** — Use `prometheus deps drift` with SBOM and
   metadata snapshots to understand upgrade momentum.
5. **Upgrade planning** — Generate commands via `prometheus deps upgrade`; run
   with `--apply --yes` to execute vetted updates.
6. **Packaging** — Build the wheelhouse with `prometheus offline-package`,
   ensuring successful guard status before promotion.
7. **Mirroring** — Distribute artefacts using `scripts/mirror_manager.py` and
   archive manifests (`vendor/packaging-run.json`, `vendor/CHECKSUMS.sha256`).
8. **Air-gapped hydration** — Bootstrap offline sites with
   `scripts/bootstrap_offline.py` and verify health using
   `prometheus offline-doctor`.
9. **Telemetry feedback** — Push guard snapshots, packaging telemetry, and CLI
   spans to observability pipelines and the governance ledger.

## Implementation status snapshot

- **Contract & policy extensions** — **Delivered**: signature policy, snoozes,
  environment alignment, and update windows now surface in guard reports.
- **Signature enforcement & snooze expiry** — **Delivered**: guard enforces
  policies with unit coverage; planner parity remains optional follow-up.
- **Mirror management CLI** — **Delivered**: `prometheus deps mirror
--status/--update` validates signatures and reports hygiene.
- **Snapshot lifecycle automation** — **In progress**: CLI provisions Temporal
  schedules; nightly CI cadence and notifications still need wiring.
- **Observability instrumentation** — **In progress**: guard, planner, and
  `deps status` emit spans/metrics; dashboards and remaining CLI commands must
  adopt the helper.
- **Scheduler payload normalisation** — **In progress**: coercion helpers ship;
  broaden test permutations for mixed-case booleans and invalid enums.
- **Model registry governance** — **Planned**: add cadence and signature
  checks to `scripts/download_models.py` with operator reporting.
- **Guided operator remediation** — **Planned**: design interactive prompts
  when guard severity crosses thresholds.
- **Dashboard & runbook rollout** — **Planned**: extend Grafana coverage and
  publish operator guides for schedule management and error recovery.

## Current gaps and follow-ups

- **Snapshot cadence** — Wire nightly guard runs, Temporal cron refresh, and
  notification fan-out into CI (`dependency-preflight.yml`).
- **Telemetry dashboards** — Extend Grafana (or chosen platform) with planner
  success rates, schedule lag, and CLI usage metrics; ensure all `prometheus
deps` subcommands emit through the telemetry helper.
- **Schedule payload tests** — Cover invalid enum values, mixed-case booleans,
  and failure modes inside `tests/unit/test_dependency_snapshot_workflow.py`.
- **SDK/serializer parity** — Surface new contract metadata (signatures,
  snoozes, environment policies) consistently across generated clients.
- **Model registry governance** — Enforce cadence and signature validation for
  model downloads with actionable reporting for operators.
- **Guided remediation** — Introduce CLI prompts that translate guard severity
  into step-by-step remediation for non-technical operators.

## Backlog by owner

- **Snapshot lifecycle automation** — _In progress_ (platform-automation): wire
  nightly CI cadence, Temporal cron hooks, and operator runbook.
- **Observability instrumentation** — _In progress_ (observability guild):
  update dashboards and ensure all CLI commands share the telemetry helper.
- **Mirror signature regression tests** — _Complete_ (qa-foundation): add
  CLI-level exit validation when bandwidth allows.
- **Schedule payload normalisation tests** — _Planned_ (platform-automation):
  broaden permutations and document operator-facing errors.
- **Model registry governance** — _Planned_ (model-platform): verify cadence
  and signature enforcement in `scripts/download_models.py` with reporting.
- **Guided operator remediation prompts** — _Planned_ (dependency-governance
  squad): design interactive CLI flows for elevated guard severity.
- **Temporal credentials & notifications** — _Planned_ (platform-automation):
  confirm secrets coverage and notification endpoints across environments.
- **Stakeholder communications** — _Planned_ (programme leads): coordinate
  release notes and change announcements for each delivery phase.

## Operational runbooks

- **Routine health check** — Run `prometheus deps status`, inspect the latest
  guard snapshot under `var/upgrade-guard/`, and confirm the Temporal schedule
  via `prometheus deps snapshot ensure`.
- **Promote a new wheelhouse** — Trigger the packaging workflow (CI dispatch or
  local run), validate with `prometheus offline-doctor --format table`, upload
  archives through `scripts/mirror_manager.py`, and push updated telemetry.
- **Air-gapped refresh** — Transfer the latest wheelhouse archive and
  `packaging-run.json`, hydrate with `scripts/bootstrap_offline.py`, then
  re-run guard/planner commands offline using mirrored SBOM and metadata.

## Artefact inventory

- **Contract profile** — `configs/dependency-profile.toml` (policy source of
  truth).
- **SBOM snapshots** — `var/dependency-sync/*.json` (inputs to guard/planner).
- **Guard bundles** — `var/upgrade-guard/<run-id>/` (JSON, Markdown, manifests,
  telemetry traces).
- **Upgrade plans** — `var/upgrade-guard/<run-id>/reports/plan.json`.
- **Packaging manifests** — `vendor/packaging-run.json`,
  `vendor/CHECKSUMS.sha256`, and platform manifests under
  `vendor/wheelhouse/platforms/`.
- **Observability exports** — Prometheus metrics and OpenTelemetry spans
  emitted by guard, planner, and CLI commands for dashboard ingestion.

For deeper workflow walkthroughs and CLI examples, pair this handbook with
`docs/packaging-workflow-integration.md` and the stage-level READMEs co-located
with the code.
