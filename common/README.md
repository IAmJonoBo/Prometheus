# Common

This package holds the shared contracts and utilities that keep Prometheus
modules loosely coupled yet interoperable. It mirrors the guidance in
`Promethus Brief.md` and `docs/architecture.md`.

## Responsibilities

- Define event schemas for each stage (`ingestion`, `retrieval`,
  `reasoning`, `decision`, `execution`, `monitoring`) plus supporting
  capabilities (forecasting, causality, risk, collaboration, observability,
  security, accessibility, governance).
- Provide base dataclasses and helpers that enforce event metadata:
  `event_id`, `correlation_id`, timestamps, actor, security labels, evidence
  references, and schema version.
- Expose utilities for serialisation, validation, masking, and observability so
  stages emit consistent metrics, traces, and logs.
- Surface typed client interfaces for optional services (model gateway,
  plugin manifests, policy engine) without leaking concrete
  implementations.

## Conventions

- Keep modules stage-agnostic; if logic belongs to a specific stage, move it to
  that stage and depend only on the published contracts here.
- Version schemas using semantic versioning. Breaking changes require
  deprecation notices, migration helpers, and documentation updates in
  `docs/capability-map.md` and stage READMEs.
- Validate payloads with `pydantic`/`dataclasses` plus lightweight runtime
  checks. Raise explicit errors that include decision or correlation IDs
  for traceability.
- Guard any helper touching sensitive data with masking or tokenisation
  options so downstream logs remain PII-free.

## Testing

- Unit tests for contracts live under `tests/common/` (to be scaffolded)
  and should cover serialisation round-trips, schema evolution, and
  masking behaviour.
- Integration suites replay golden event fixtures to ensure backward
  compatibility before promoting schema changes.

## Roadmap

- Publish concrete schema modules for every stage (currently placeholders).
- Generate OpenAPI/JSON Schema artefacts from the contracts for client SDKs.
- Provide a shared observability helper once the telemetry library lands.
- Document plugin manifest dataclasses once the loader spec is finalised.
