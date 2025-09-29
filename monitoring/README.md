# Monitoring

The monitoring stage provides feedback loops, telemetry aggregation, and
incident handling across the pipeline.

## Responsibilities

- Collect metrics from each stage and publish consolidated `MonitoringSignal`
  events.
- Detect anomalies, SLO breaches, and risk threshold violations (roadmap).
- Feed learnings back into reasoning, policy, and execution playbooks.
- Guard against Goodhart's Law by validating metric pairs and anti-gaming tests.

## Inputs & outputs

- **Inputs:** Stage telemetry samples and optional extra metrics from pipeline
  stages (for example, ingestion run metrics).
- **Outputs:** `MonitoringSignal` events containing metric samples, incident
  placeholders, and descriptive text.
- **Shared contracts:** `common/contracts/monitoring.py` defines
  `MonitoringSignal` and `MetricSample`. Cross-reference guidance in
  `docs/performance.md` and `docs/quality-gates.md`.

## Components

- `build_collector` wires Prometheus Pushgateway and OpenTelemetry collectors
  when optional dependencies are installed, falling back to in-memory
  storage otherwise.
- `MonitoringService` aggregates metrics into `MonitoringSignal` events and
  forwards them to configured collectors.
- Extend log/alert pipelines once additional collectors and sinks are
  implemented.

## Observability

- Record collector readiness in integration tests and broaden coverage to
  alert pipelines once implemented.

## Backlog

- Implement schema validation for telemetry payloads in `tests/`.
- Automate calibration tracking dashboards referenced in `docs/performance.md`.
- Document incident response playbooks in `docs/quality-gates.md`.
