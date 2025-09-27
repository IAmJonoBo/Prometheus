# Prometheus

Prometheus is an OSS-first, modular, event-driven strategy OS for
evidence-linked decision automation. It orchestrates the full life cycle from
ingesting raw intelligence to monitoring execution outcomes, preserving
citations and governance signals at each step.

## System flow

The core pipeline passes typed events through six stages:

1. **Ingestion** — Connectors normalise sources, scrub PII, and attach
   provenance metadata.
2. **Retrieval** — Hybrid lexical/vector search returns scored passages with
   governed access controls.
3. **Reasoning** — Orchestrators break work into tool calls, critique loops, and
   evidence-linked narratives.
4. **Decision** — Policy engines classify decision criticality, enforce
   approvals, and write structured ledger entries.
5. **Execution** — Syncs approved plans to delivery tools and maintains
   idempotent change history.
6. **Monitoring** — Tracks KPIs, risks, and incidents to trigger adaptation and
   close the learning loop.

See `docs/architecture.md` for sequence diagrams and data contracts, and
`docs/model-strategy.md` for model routing strategy details.

## Repository layout

- `ingestion/` — Source adapters, schedulers, and normalisers.
- `retrieval/` — Index builders, rerankers, and query orchestration.
- `reasoning/` — Agent workflows, critique loops, and evidence synthesis.
- `decision/` — Policy evaluation, ledger records, and approval flows.
- `execution/` — Integrations that dispatch work to downstream systems.
- `monitoring/` — Telemetry collectors, dashboards, and feedback hooks.
- `plugins/` — Optional capabilities packaged for isolated deployment.
- `common/` — Shared contracts, event schemas, and utilities.
- `docs/` — Product brief, capability map, topic guides, and ADRs.
- `tests/` — Unit, integration, and end-to-end suites mirroring the pipeline.

## Getting started

1. Review `docs/overview.md` for the mission and success criteria.
2. Read the stage README for the area you are modifying (e.g.,
   `retrieval/README.md`).
3. Follow environment setup guidance in `configs/README.md` once services are
   ready to configure.

Sample datasets, docker-compose profiles, and automation scripts will land in
future iterations. Track progress in `docs/ROADMAP.md`.

## Development practices

- Keep modules self-contained and communicate via published events.
- When adding code, include unit tests inside the relevant stage and update
  cross-stage integration suites as needed.
- Record major design changes as ADRs in `docs/ADRs/` and link them from the
  affected documentation.
- Adhere to linting rules (80-character markdown lines, repository formatting
  configs) by running the local pre-commit hooks before opening a PR.

For contribution details, see `docs/developer-experience.md` and the
`CONTRIBUTING.md` guide in `docs/`.
