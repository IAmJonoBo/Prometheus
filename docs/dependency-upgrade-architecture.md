# Dependency Upgrade Architecture

## Overview

This document lays out the end-to-end design for keeping Prometheus
dependencies, sub-dependencies, and model artifacts current while preserving
stability across local, CI, and air-gapped environments.

The approach combines richer telemetry, automated drift analysis, a guided
autoresolver, and artifact lifecycle controls. Every environment consumes the
same signed metadata snapshots so upgrade decisions are deterministic and
auditable.

## Components

1. **Telemetry & SBOM generation**
   - Extend `scripts/sync-dependencies.py` to emit a CycloneDX SBOM capturing
     all resolved packages, markers, and hashes. SBOMs live in
     `var/upgrade-guard/sbom/` with retention configured per policy.
   - Contract gains `policies.update_window`,
     `policies.allow_transitive_conflicts`, and per-package pin intents (e.g.,
     `stay_on_major`).
   - Metadata snapshots (`var/upgrade-guard/index/<timestamp>.json`) track
     latest versions obtained from PyPI mirrors or pre-exported feeds.

2. **Dependency drift analysis**
   - New module `scripts/dependency_drift.py` loads SBOM + metadata snapshots,
     comparing current pins to available versions.
   - Emits `DependencyDriftReport` with per-package status (`up-to-date`,
     `patch_available`, `minor_available`, `major_available`, `conflict`).
   - Generates upgrade recommendations respecting contract policies (allowed
     majors/minors) and highlights resolver conflicts.

3. **Upgrade guard integration**
   - `scripts/upgrade_guard.py` imports the drift report, merging it with
     preflight, Renovate, CVE, and contract signals.
   - Summary severity escalates based on drift exceeding `update_window` or
     unresolved conflicts. Markdown output includes drift tables and SBOM
     references.
     - The `prometheus upgrade-guard` CLI accepts `--sbom`, `--metadata`, and
       snapshot lifecycle flags (`--snapshot-root`, `--snapshot-retention-days`,
       `--sbom-max-age-days`) so operators can feed fresh artefacts while the
       guard enforces cadence and retention automatically.
     - Snapshot runs are written to `var/upgrade-guard/<run-id>/` with copied
       inputs and manifests so evidence is auditable across environments.
   - Guard emits `UpgradeOpportunityDetected` events for downstream
     automation.
     - Contract metadata extraction surfaces additional governance context in
       the guard report so reviewers can see why a severity was assigned: - **Signature policy** captures whether signed artefacts are required,
       which publishers are trusted, enforcement scope (artefacts or
       attestations), and any grace periods. When the guard later verifies
       signatures, these settings drive escalation rules and inform the
       Markdown summary. - **Snoozes** list approved temporary exceptions with scope, reason,
       and expiration timestamps. The guard preserves the audit trail in
       its machine-readable output so downstream automation can honour the
       snooze window yet still alert when it lapses. - **Environment alignment** defines per-environment profiles, lockfile
       cadences, and alert channels. The guard emits this context for
       dashboards and future Phase 3 logic that will escalate stale lockfiles
       or unsigned artefacts per environment policy.

4. **CLI orchestration**
   - **Shipping today** - `prometheus upgrade-guard`: Runs the guard and drift analysis,
     printing a risk summary and persisting snapshots. - `prometheus upgrade-planner`: Generates a resolver-backed upgrade plan
     from SBOM + metadata artefacts, emitting JSON and recommended
     `poetry update` commands. - `prometheus deps status`: Aggregates guard and planner outputs into
     a single status report, supports profile overrides via
     `--profiles NAME=PATH`, optional planner toggles, and exports
     machine-readable JSON with `--json` for CI pipelines. - `prometheus deps upgrade --plan auto`: Invokes the weighted
     autoresolver, renders a scoreboard with per-package score
     breakdowns, and optionally executes the recommended `poetry`
     commands when `--apply --yes` is supplied. If `--project-root` is
     omitted the command runs from the SBOM's directory, mirroring the
     planner defaults. - `prometheus deps snapshot ensure`: Provisions or refreshes the
     Temporal dependency snapshot schedule using configuration
     payloads that mirror guard inputs. The command executes inside
     AnyIO so the CLI stays responsive while interacting with Temporal.
   - **Planned (`deps` suite)** - `prometheus deps mirror --status|--update`: Manages wheel/model
     mirrors for air-gapped sites, validating signatures and freshness
     before promoting new artefacts. - Guided CLI prompts will surface remediation steps for
     non-technical operators whenever drift or guard severity crosses
     policy thresholds.

5. **Intelligent autoresolver**
   - Weighted scoring model evaluates candidate upgrades using recency,
     severity, contract allowances, test coverage history, and resolver success
     probability.
   - Produces `UpgradePlan` objects with recommended command snippets (e.g.,
     `poetry update packageA packageB`) and expected risk level.
   - Integrates with `poetry` in dry-run mode to verify lockfile solvability
     before suggesting updates. Plans that fail are tagged `blocked`, and
     successful plans surface score breakdowns used by the CLI scoreboard.

6. **Model registry governance**
   - New `models/registry.toml` enumerates approved providers, desired
     channels, and validation cadence.
   - `scripts/download_models.py` reads the registry to check for newer models,
     verifying signed metadata before prompting downloads.

7. **CI & scheduling**
   - Dependency-preflight workflow gains a nightly schedule plus PR triggers
     for dependency-related files.
   - Guard artefacts (SBOM, drift report, upgrade plan) are uploaded when
     severity ≥ `needs-review`.
   - Temporal cron job runs weekly to refresh snapshots and send
     notifications. The `prometheus deps snapshot ensure` CLI wraps the
     schedule ensure workflow so operators can seed or refresh the Temporal
     job from CI or local environments with identical payloads.

8. **Artifact lifecycle**
   - Temporary artefacts (SBOMs, lock snapshots, wheel caches) are cleaned
     post-success via `scripts/manage-deps.sh --prune` and CI steps.
   - Persistent mirrors are stored outside the repo under
     `vendor/wheelhouse/` and `vendor/models/`, but scrubbed locally after
     packaging.

9. **Todo persistence**
   - Repository-level manifest `docs/dependency-upgrade-todos.md` tracks
     outstanding upgrade tasks so context is shared across contributors.

10. **Testing & observability**
    - Unit tests cover drift analysis, autoresolver scoring, CLI flows, and
      cleanup routines.
    - Logs and OpenTelemetry spans emitted from guard and CLI for visibility.

## Workflow Summary

1. Developer runs `prometheus deps status`; guard loads SBOM + snapshots,
   prints status, and shares upgrade plan.
2. If plan suggests updates, developer executes
   `prometheus deps upgrade --plan auto`, which prints the weighted scoreboard
   and, when invoked with `--apply --yes`, applies the top-ranked commands
   from the SBOM directory by default.
3. CI pipeline runs guard on PRs and nightly; failing severity gates stop
   merges until addressed.
4. Air-gapped sites refresh snapshots via `prometheus deps mirror --update`,
   then run guard offline.
5. After successful CI builds, temporary artifacts are pruned, ensuring no
   stale data lingers on runners.

## Phase 3 & 4 roadmap alignment

The following items track the active implementation plan. They mirror the
engineering todo list so documentation and delivery stay in lockstep:

1. **Contract and policy extensions** _(delivered)_
   - `configs/dependency-profile.toml` now captures signature requirements,
     environment alignment, and snooze windows, and the guard surfaces these
     settings in its reports.
2. **Signature checks & snooze logic** _(delivered)_
   - Guard execution performs signature verification, respects snooze expiry,
     and escalates severity; planner parity remains an optional follow-up.
3. **CLI & pipeline exposure** _(in progress)_
   - `prometheus deps mirror --status|--update` and guard CLI toggles are
     available; pipeline automation still needs to expose new knobs and
     schedule recurring runs.
4. **Testing and automation** _(delivered)_
   - Unit coverage now verifies signature policy enforcement, snooze expiry,
     and snapshot retention.
5. **Documentation & rollout** _(in progress)_
   - Governance and operator references require updates as features land, with
     rollout guidance tracked alongside remaining automation work.

## Implementation status _(updated 2025-10-03)_

### Shipped

- CycloneDX SBOM export via `scripts/sync-dependencies.py` with
  artefact retention hooks.
- Contract policy extensions (`update_window`, `allow_transitive_conflicts`,
  `stay_on_major`) flowing into drift evaluation.
- Drift analysis pipeline (`scripts/dependency_drift.py`) and planner
  integrations with tested CLI entry points.
- Upgrade guard snapshots, governance context (signature policy, snoozes,
  environment alignment), and `prometheus deps status` aggregation with JSON
  export.
- Upgrade guard signature enforcement, snooze expiry handling, and
  accompanying OpenTelemetry/Prometheus instrumentation.
- Planner and dependency CLI instrumentation emitting OpenTelemetry spans and
  Prometheus metrics for dependency status aggregation.
- `prometheus deps mirror --status|--update` shipped with signature validation
  and mirror hygiene reporting.
- Upgrade planner core flow, resolver dry-runs, and documentation updates for
  guard/planner usage.
- Weighted autoresolver scoring with score breakdowns and
  `prometheus deps upgrade --plan auto` automation (including optional
  command execution, SBOM-relative defaults, and scoreboard output).
- Temporal dependency snapshot schedule automation via
  `prometheus deps snapshot ensure`, including request coercion that
  normalizes scheduler payload booleans and planner package overrides.
- Artefact lifecycle tasks (`scripts/manage-deps.sh --prune`, wheelhouse
  hygiene) aligned with repo storage expectations.
- Repository-wide todo manifest (`docs/dependency-upgrade-todos.md`) capturing
  outstanding items and owners for dependency governance work.

### Planned / backlog

- Snapshot scheduling automation (nightly CI cadence, Temporal cron refresh,
  notifications) building on the existing snapshot index lifecycle.
- Dashboards surfacing planner/CLI telemetry along with instrumentation for
  additional dependency CLI subcommands.
- Model registry governance enhancements (signature verification, cadence
  enforcement, operator reporting).
- Guided operator prompts and remediation flows for non-technical users when
  guard severity crosses policy thresholds.
