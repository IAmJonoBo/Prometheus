# Prometheus

Prometheus is an OSS-first, modular, event-driven strategy OS for
evidence-linked decision automation. It orchestrates the full life cycle from
ingesting raw intelligence to monitoring execution outcomes, preserving
citations and governance signals at each step.

Prometheus exposes configuration profiles for laptop, self-hosted, or
multi-tenant SaaS deployments. Future releases will automate hardware
benchmarking, but the current build expects operators to pick the
profile that matches their environment. Optional plugins extend
capabilities without leaking stage-specific concerns.

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

- `api/` — FastAPI service that exposes pipeline runs over HTTP.
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
- `infra/` — Docker Compose definitions for Postgres, OpenSearch, Qdrant,
  Temporal, Prometheus, and Grafana.
- `web/` — Next.js workspace scaffolding for the collaboration UI.
- `desktop/` — Tauri shell wrapping the web UI for offline-first deployments.

## Runtime profiles & packaging

- **Desktop / laptop:** Single-process deployment with quantised models and
  local storage for organisations getting started.
- **Self-hosted server:** Each stage can scale horizontally behind queues
  with per-tenant encryption and RBAC enforced by event metadata.
- **SaaS multi-tenant:** Canary releases, feature flags, and signed artefacts
  keep hosted deployments within the quality and compliance gates defined in
  the brief.
- **CLI / SDK:** The Typer CLI (`poetry run prometheus …`) and Python SDK
  (`sdk/`) exercise ingestion, decision, and monitoring flows for automated
  rehearsals.

## Getting started

1. Review `docs/overview.md` for the mission and success criteria.
2. Read the stage README for the area you are modifying (e.g.,
   `retrieval/README.md`).
3. Launch the optional external stack from `infra/` when you need Postgres,
   Temporal, or search backends locally (`cd infra && docker compose up -d`).
4. Follow environment setup guidance in `configs/README.md` once services are
   ready to configure.
5. Review `docs/tech-stack.md` to align local tooling with the reference stack
   before introducing new dependencies or providers.

Sample datasets ship in `docs/samples/`, and the infrastructure compose
profiles now live under `infra/`. Track broader progress in `docs/ROADMAP.md`.

## Bootstrap pipeline

After installing dependencies (`poetry install` or equivalent), run the
bootstrap pipeline:

```bash
poetry run prometheus pipeline --query "configured"
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
- attempts to dispatch execution via Temporal when configured. If the
  optional `temporalio` dependency is missing or a call fails, the
  resulting event records the failure note. Set
  `execution.sync_target = "webhook"` or leave it at the default
  in-memory adapter to avoid Temporal when the service is unavailable.
- pushes monitoring metrics to a Prometheus Pushgateway if reachable and mirrors
  them through the OpenTelemetry console exporter.
- generates a Temporal worker bootstrap plan (host, namespace, task queue,
  telemetry endpoints) and default Grafana dashboards for ingestion and
  pipeline health that you can import directly into an observability stack.

You can override any stage configuration by copying the default TOML and
switching adapters (for example, keep everything in-memory during local
development by setting `ingestion.persistence.type = "memory"` and
`execution.sync_target = "in-memory"`).

### Local-friendly profile

If you are running the bootstrap pipeline without OpenSearch, Qdrant, or
Temporal services, use the bundled local profile instead:

```bash
poetry run prometheus pipeline \
  --config configs/defaults/pipeline_local.toml \
  --query "configured"
```

The local profile keeps ingestion sources limited to the repository samples,
switches retrieval to RapidFuzz with keyword overlap reranking, and uses the
in-memory execution adapter so the pipeline can complete without external
dependencies.

### Run the HTTP API

Spin up the FastAPI layer once dependencies are installed:

```bash
poetry run prometheus-api
```

Set `PROMETHEUS_CONFIG` to point at an alternative TOML configuration and
`API_RELOAD=true` for auto-reload during development. When the `infra/
docker-compose.yaml` stack is running, the API health check and Prometheus
metrics endpoint (`/metrics`) will surface connectivity issues for external
services.

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
