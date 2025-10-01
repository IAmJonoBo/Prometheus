# Observability Scaffolding

Prometheus ships with a minimal observability toolkit so teams can go from
local bootstrap to production telemetry without guessing which signals to
collect. This document outlines the worker plan and dashboard artefacts
introduced in the bootstrap flow.

## Temporal worker plan

The module `execution.workers` produces a `TemporalWorkerPlan` containing:

- **Connection details** – host, namespace, and task queue pulled from
  `execution.worker` configuration or the Temporal execution adapter.
- **Instrumentation endpoints** – Prometheus scrape port, OTLP endpoint, and
  dashboard identifiers for downstream automation.
- **Status notes** – whether the `temporalio` dependency is available and ready
  to start a worker, or if the plan is running in scaffolding-only mode.

Use the plan to drive infrastructure provisioning or to render operational run
books. The `describe()` helper offers a compact log/string summary for CLI
reporting.

### Validating connectivity

Run `prometheus temporal validate` to exercise the plan against a live stack.
The command probes the Temporal gRPC host, Prometheus scrape port, and OTLP
collector defined in `execution.worker.metrics`. Pass
`--export-dashboards <directory>` to materialise the configured Grafana
dashboards as JSON files that can be imported directly into a running Grafana
instance.

## Grafana dashboards

`monitoring.dashboards` now exposes two default Grafana boards:

1. **Prometheus Ingestion Overview** – scheduler throughput, PII redactions, and
   per-connector latency slices.
2. **Prometheus Pipeline Overview** – retrieval success rate, decision approval
   velocity, and recent incident diagnostics.

You can append custom dashboards via `[[monitoring.dashboards]]` entries in
`configs/defaults/pipeline.toml`. Each entry maps directly onto the
`GrafanaDashboard` dataclass, allowing you to check dashboards into source
control and keep reviewable diffs for observability changes.
