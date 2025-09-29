# Execution

The execution stage dispatches approved decisions to downstream systems and
tracks resulting activity.

## Responsibilities

- Convert ledger-approved decisions into sync notes through the configured
  adapter (Temporal, webhook, or in-memory).
- Ensure adapters report idempotent work packages to avoid duplicate syncs.
- Propagate status updates and impact metrics back into the decision ledger.
- Emit `ExecutionPlanDispatched` events containing sync metadata.

## Inputs & outputs

- **Inputs:** `DecisionRecorded` events plus adapter configuration.
- **Outputs:** `ExecutionPlanDispatched` events with sync targets, work
  packages, and adapter notes.
- **Shared contracts:** `common/contracts/execution.py` defines
  `ExecutionPlanDispatched` and `WorkPackage`. Coordinate documentation with
  `docs/performance.md` and `docs/ux.md`.

## Components

- `TemporalExecutionAdapter` launches workflows via `temporalio` when the
  dependency is installed and the Temporal cluster is reachable.
- `WebhookExecutionAdapter` provides HTTP dispatch with status reporting and
  retry-friendly error messages.
- `_InMemoryExecutionAdapter` captures sync notes for local development and
  tests.
- Temporal worker planning occurs through `build_temporal_worker_plan` and
  `create_temporal_worker_runtime`, exposing readiness metadata to the
  pipeline orchestrator.

## Observability

- The orchestrator records adapter notes on each dispatch; once telemetry
  sinks are hooked up these notes can be promoted to structured metrics.
- Temporal worker instrumentation exposes Prometheus and OTLP endpoints when
  dependencies are installed and configured.

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
- Integrate Temporal worker runtime checks into staging deploy pipelines.
