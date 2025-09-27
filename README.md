# Prometheus

Prometheus is an OSS-first, modular, event-driven strategy OS for
evidence-linked decision automation. It orchestrates the full life cycle from
ingesting raw intelligence to monitoring execution outcomes, preserving
citations and governance signals at each step.

Prometheus auto-benchmarks its environment to pick sensible defaults and
selects laptop, self-hosted, or multi-tenant SaaS profiles automatically.
Optional plugins extend capabilities without leaking stage-specific concerns.

## System flow

The core pipeline passes typed events through six stages:

1. **Ingestion** — Connectors normalise filesystem, web, and synthetic sources,
   persist artefacts, scrub PII, and attach provenance metadata.
2. **Retrieval** — Hybrid lexical/vector search (RapidFuzz, OpenSearch, and
   Qdrant with cross-encoder reranking) returns scored passages with governed
   access controls.
3. **Reasoning** — Orchestrators break work into tool calls, critique loops, and
   evidence-linked narratives.
4. **Decision** — Policy engines classify decision criticality, enforce
   approvals, and write structured ledger entries.
5. **Execution** — Syncs approved plans to delivery tools and maintains
   idempotent change history.
6. **Monitoring** — Tracks KPIs, risks, and incidents to trigger adaptation and
   close the learning loop.

See `docs/architecture.md` for sequence diagrams and data contracts,
`docs/model-strategy.md` for model routing strategy details, and
`docs/tech-stack.md` for the canonical OSS-first toolchain.

## Repository layout

- `ingestion/` — Source adapters, schedulers, and normalisers (filesystem, web,
  synthetic connectors, and document stores).
- `retrieval/` — Index builders, rerankers, and query orchestration (hybrid
  lexical/vector backends).
- `reasoning/` — Agent workflows, critique loops, and evidence synthesis.
- `decision/` — Policy evaluation, ledger records, and approval flows.
- `execution/` — Integrations that dispatch work to downstream systems.
- `monitoring/` — Telemetry collectors, dashboards, and feedback hooks.
- `plugins/` — Optional capabilities packaged for isolated deployment.
- `common/` — Shared contracts, event schemas, and utilities.
- `docs/` — Product brief, capability map, topic guides, and ADRs.
- `tests/` — Unit, integration, and end-to-end suites mirroring the pipeline.

## Runtime profiles & packaging

- **Desktop / laptop:** Single-process deployment with quantised models and
  local storage for organisations getting started.
- **Self-hosted server:** Each stage can scale horizontally behind queues
  with per-tenant encryption and RBAC enforced by event metadata.
- **SaaS multi-tenant:** Canary releases, feature flags, and signed artefacts
  keep hosted deployments within the quality and compliance gates defined in
  the brief.
- **CLI / SDK:** Lightweight clients exercise ingestion, decision, and
  monitoring flows for automated rehearsals.

## Getting started

1. Review `docs/overview.md` for the mission and success criteria.
2. Read the stage README for the area you are modifying (e.g.,
   `retrieval/README.md`).
3. Follow environment setup guidance in `configs/README.md` once services are
   ready to configure.
4. Review `docs/tech-stack.md` to align local tooling with the reference stack
   before introducing new dependencies or providers.

Sample datasets, docker-compose profiles, and automation scripts will land in
future iterations. Track progress in `docs/ROADMAP.md`.

## Bootstrap pipeline

After installing dependencies (`poetry install` or equivalent), run the
bootstrap pipeline:

```bash
poetry run python -m prometheus --query "configured"
```

The command loads `configs/defaults/pipeline.toml`, executes all stages with the
configured connectors, and prints the resulting decision, execution notes, and
monitoring signal. The default profile:

- normalises Markdown samples under `docs/samples`, pulls a reference web page
  with Trafilatura, and persists artefacts in `var/ingestion.db`.
- schedules ingestion connectors asynchronously with bounded concurrency,
  retries, and rate limiting while masking PII using the built-in Presidio
  redactor before storing artefacts (install with `poetry install --extras pii`
  to enable local detection).
- performs hybrid retrieval with RapidFuzz (lexical), OpenSearch (BM25), and a
  Qdrant vector backend backed by Sentence-Transformers embeddings with an
  optional cross-encoder reranker for precision gains.
- attempts to dispatch execution via Temporal and fallbacks to webhook/in-memory
  when the host is unavailable, logging the outcome to the event bus.
- pushes monitoring metrics to a Prometheus Pushgateway if reachable and mirrors
  them through the OpenTelemetry console exporter.
- generates a Temporal worker bootstrap plan (host, namespace, task queue,
  telemetry endpoints) and default Grafana dashboards for ingestion and
  pipeline health that you can import directly into an observability stack.

You can override any stage configuration by copying the default TOML and
switching adapters (for example, keep everything in-memory during local
development by setting `ingestion.persistence.type = "memory"` and
`execution.sync_target = "in-memory"`).

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
