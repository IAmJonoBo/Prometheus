# Dependency Upgrade Execution Tracker

Updated: 2025-10-03

This tracker mirrors the actionable backlog for the dependency upgrade initiative.
Each entry references the corresponding phase outlined in
`docs/dependency-governance.md` and is mapped to the accountable owner.

## Phase 1 – Snapshot cadence automation

**Owners:** platform-automation

- [x] Add nightly schedule to `dependency-preflight.yml`.
- [x] Invoke `prometheus deps snapshot ensure` prior to guard execution.
- [x] Persist guard artefacts as workflow run outputs and publish summaries to
      Slack/email (or equivalent notification channel).
- [x] Configure Temporal cron schedule using shared payload schema and failure
      notifications.

## Phase 2 – Regression hardening

**Owners:** qa-foundation, platform-automation

- [x] Extend `tests/unit/test_dependency_snapshot_workflow.py` with mixed-case
      boolean, invalid enum, and failure-path payloads.
- [x] Add mirror signature enforcement tests covering unsigned, stale, and
      refreshed artefact scenarios.
- [x] Backfill snapshot index pruning coverage.

## Phase 3 – Observability & runbooks

**Owners:** observability guild, platform-automation

- [x] Instrument planner and CLI flows with OpenTelemetry spans and Prometheus
      metrics mirroring guard telemetry conventions.
- [ ] Extend dashboards to include planner success rate, schedule lag, and CLI
      usage metrics.
- [ ] Publish operator runbooks detailing schedule management, error recovery,
      and local CLI execution.

## Phase 4 – Operator experience & governance

**Owners:** dependency-governance squad, model-platform

- [ ] Implement guided remediation prompts for `prometheus deps` commands when
      guard severity thresholds are crossed.
- [ ] Enforce model registry cadence/signature verification inside
      `scripts/download_models.py` with reporting hooks.
- [ ] Ensure SDKs/serializers expose signature, snooze, and environment metadata
      fields consistently across clients.

## Cross-cutting

- [ ] Confirm Temporal namespace credentials and notification endpoints are
      available in CI secrets.
- [ ] Coordinate release notes and stakeholder communications ahead of each
      phase landing.
- [x] Provide default request/notification payloads under
      `configs/defaults/` for reuse across environments.
