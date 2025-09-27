# Plugins

Plugins provide optional capabilities without bloating the core pipeline. Each
plugin must be independently deployable and respect the event-driven contracts.

## Structure

- Place each plugin in its own directory with a descriptive name.
- Include a `README.md` describing purpose, required events, configuration, and
  failure modes.
- Surface a `manifest.(yaml|json)` (TBD) declaring subscriptions, emissions,
  permissions, and resource limits.

## Guidelines

- Do not import stage-specific helpers directly; rely on `common/` contracts or
  service endpoints.
- Keep secrets and credentials out of the plugin directory; reference
  environment variables defined in `configs/` instead.
- Emit observability signals (metrics, logs, traces) using the shared library
  once implemented.
- Provide mocks or fixtures in `tests/plugins/` to validate behaviour without
  external dependencies.

## Lifecycle

- Register plugins in the orchestration layer (TBD) to enable auto-discovery.
- Define health checks so monitoring can quarantine failing plugins.
- Document upgrade paths, including schema migrations or retraining needs.

## Backlog

- Finalise manifest format and loader implementation.
- Publish example plugins (e.g., financial data ingestion, risk scoring).
- Add plugin linting and template generator to developer tooling.
