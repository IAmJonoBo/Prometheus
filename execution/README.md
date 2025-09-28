# Execution

The execution stage dispatches approved decisions to downstream systems and
tracks resulting activity.

## Responsibilities

- Translate ledger-approved plans into concrete tasks for delivery platforms.
- Ensure idempotent sync so repeated runs do not create duplicate work.
- Propagate status updates and impact metrics back into the decision ledger.
- Emit `Execution.TaskSync` and `Execution.StatusUpdate` events.

## Inputs & outputs

- **Inputs:** `Decision.Recorded` events, team roster metadata, integration
  credentials, and schedule constraints.
- **Outputs:** `Execution.TaskSync` events (initial dispatch) and
  `Execution.StatusUpdate` events (progress, completion, blockers).
- **Shared contracts:** Define schemas in `common/contracts/execution.py`
  (placeholder) and coordinate documentation with `docs/performance.md` and
  `docs/ux.md`.

## Components

- Integration clients (Jira, Asana, email, webhook, RPA) with retry semantics.
- State reconciler to detect drift between ledger expectations and field data.
- Impact tracker mapping execution progress to strategy metrics.
- Notification layer for delivery teams and stakeholders.
- Temporal worker runtime for orchestrating workflows and activities with
  built-in observability hooks.

## Observability

- Monitor sync latency, task creation success rate, and retry volume.
- Include correlation IDs to trace updates back to original decisions.
- Log idempotency keys and reconciliation anomalies for investigation.
- Expose worker metrics via the Prometheus endpoint configured in
  `TemporalWorkerConfig.metrics.prometheus_port`.
- Forward OTLP metrics to the configured collector endpoint when available.

## Temporal worker runtime

- Use `create_temporal_worker_runtime` to bootstrap workers when the
  `temporalio` dependency is installed.
- Default workflows and activities live in `execution/workflows.py`; override
  them by providing explicit references in `TemporalWorkerConfig`.
- Worker planning captures telemetry wiring and connection details; call
  `TemporalWorkerPlan.describe()` to emit human-readable status during boots.
- The pipeline orchestrator exposes `worker_plan` and `worker_runtime` so
  integration tests and health checks can assert readiness before launches.

## Backlog

- Publish reference integration adapters with contract tests.
- Automate status polling and push hooks for key delivery platforms.
- Document escalation playbooks in `docs/ux.md` and `docs/performance.md`.
- Integrate temporal worker runtime checks into staging deploy pipelines.
