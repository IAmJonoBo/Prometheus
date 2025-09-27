# Monitoring

The monitoring stage provides feedback loops, telemetry aggregation, and
incident handling across the pipeline.

## Responsibilities

- Collect metrics, logs, traces, and cost data from each stage and plugin.
- Detect anomalies, SLO breaches, and risk threshold violations.
- Feed learnings back into reasoning, policy, and execution playbooks.
- Emit `Monitoring.Alert` and `Monitoring.Feedback` events.
- Guard against Goodhart's Law by validating metric pairs and anti-gaming tests.

## Inputs & outputs

- **Inputs:** Stage telemetry streams, external observability sinks, user
  feedback, and risk register updates.
- **Outputs:** `Monitoring.Alert` events (incidents) and
  `Monitoring.Feedback` events (trend reports, calibration deltas).
- **Shared contracts:** Define schemas in `common/contracts/monitoring.py`
  (placeholder) and cross-reference guidance in `docs/performance.md` and
  `docs/quality-gates.md`.

## Components

- Metrics pipeline (Prometheus/OpenTelemetry) with retention policies.
- Log aggregator with PII scrubbing and search interface.
- Alert router pushing notifications to incident management tools.
- Feedback analyzer that reconciles forecast accuracy and user sentiment.

## Observability

- Dogfood the same monitoring toolchain used for other stages.
- Track alert precision/recall and mean time to detect/respond.
- Publish weekly health reports linking incidents to roadmap follow-ups.

## Backlog

- Implement schema validation for telemetry payloads in `tests/`.
- Automate calibration tracking dashboards referenced in `docs/performance.md`.
- Document incident response playbooks in `docs/quality-gates.md`.
