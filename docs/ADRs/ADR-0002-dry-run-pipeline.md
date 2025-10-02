# ADR-0002: Dry-Run Pipeline Orchestration

## Status

Accepted

## Context

Prometheus orchestrates an event-driven pipeline across ingestion, retrieval,
reasoning, decision, execution, and monitoring stages. Production runs depend on
live connectors, mutable data stores, and third-party integrations. We need a
deterministic way to execute the entire pipeline end-to-end for regression
validation, dependency upgrades, and incident rehearsals without touching
production systems. The existing tooling covers offline packaging but lacks an
orchestrated dry-run mode, pipeline-wide telemetry, or governance hooks to
triage failures from CI.

## Decision

We will introduce a dedicated dry-run orchestration layer that:

1. Exposes a `pipeline dry-run` command in the Prometheus CLI and a matching
   GitHub Actions workflow.
2. Executes every stage with a `DryRunContext` that swaps production I/O for
   sandbox fixtures, shadow event routing, and deterministic mocks.
3. Persists stage outputs, metrics, traces, and summary artifacts under
   versioned run directories for postmortem analysis.
4. Publishes structured telemetry to the existing observability stack with
   `mode="dry-run"` labels, retaining data for 30 days.
5. Routes failures into the governance layer through `CIFailureEvent` events,
   automated issue creation, and lineage tracking.
6. Powers an upgrade guard strategy that inspects dependency preflight reports,
   Renovate metadata, and CVE feeds to recommend remediation work.

## Consequences

- Pros
  - Safer validation of dependency updates and refactors, uncoupled from
    production incidents.
  - Rich observability for every stage, enabling faster debugging and
    historical comparisons.
  - Automated governance workflows that surface regressions to stakeholders promptly.
  - Reusable replay tooling for reproducing failures across services.

- Cons
  - Additional complexity in the event bus and configuration stack to support
    dry-run isolation.
  - Increased CI runtime and artifact storage requirements that mandate
    retention policies.
  - Ongoing maintenance of fixture fidelity and mock parity with production integrations.

## Follow-Up Work

- Build the dry-run CLI command, shadow bus, and fixture loaders.
- Extend monitoring dashboards, retention jobs, and governance hooks to consume
  dry-run telemetry.
- Document runbooks and testing strategies for the new workflow, including
  upgrade guard scoring and rollback procedures.
