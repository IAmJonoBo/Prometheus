# Prometheus

**Status**: Active Development | [Current Status](CURRENT_STATUS.md) | [Roadmap](docs/ROADMAP.md) | [Future Vision](FUTURE_ENHANCEMENTS.md)

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

**Quick Links:**
- 📊 [Current Status & Health](CURRENT_STATUS.md) - What works today
- 📖 [Documentation](docs/README.md) - Full documentation index
- 🚀 [Getting Started Guide](docs/getting-started.md) - Detailed setup instructions
- 🏗️ [Architecture Overview](docs/architecture.md) - System design
- 📋 [Roadmap](docs/ROADMAP.md) - Near-term plans
- 🎯 [Future Vision](FUTURE_ENHANCEMENTS.md) - Long-term enhancements

**Setup Steps:**
1. Review `docs/overview.md` for the mission and success criteria.
2. Follow the [Getting Started Guide](docs/getting-started.md) for environment setup.
3. Read the stage README for the area you are modifying (e.g.,
   `retrieval/README.md`).
4. Launch the optional external stack from `infra/` when you need Postgres,
   Temporal, or search backends locally (`cd infra && docker compose up -d`).
5. Review `docs/tech-stack.md` to align local tooling with the reference stack
   before introducing new dependencies or providers.

Sample datasets ship in `docs/samples/`, and the infrastructure compose
profiles now live under `infra/`. Track broader progress in `docs/ROADMAP.md`.

### Local virtual environment

This repository pins Poetry to create a project-local virtual environment in
`.venv/`, ensuring dependencies live alongside the checkout on the external
volume. Run `poetry install` to materialise the environment.
Activate it with `source .venv/bin/activate` on macOS or Linux, or
`.\venv\Scripts\activate` on Windows when you need the interpreter outside
Poetry commands.

At import time the toolkit now defaults Hugging Face, Sentence-Transformers,
and spaCy caches to `vendor/models/`, ensuring model downloads land on the
same external volume as the repository without extra configuration.

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

## Integrated CLI commands

The Prometheus CLI provides unified commands for packaging, dependency
management, and diagnostics:

### Orchestration (New!)

Complete workflow automation for seamless local-remote integration:

```bash
# Check current orchestration state
prometheus orchestrate status

# Full dependency workflow: preflight → guard → upgrade → sync
prometheus orchestrate full-dependency --auto-upgrade --force-sync

# Full packaging workflow: wheelhouse → offline-package → validate → remediate
prometheus orchestrate full-packaging --validate

# Sync remote CI artifacts to local environment
prometheus orchestrate sync-remote ./offline-packaging-suite-optimized
```

See [docs/orchestration-enhancement.md](docs/orchestration-enhancement.md) for comprehensive guide.

### Offline packaging workflow

```bash
# Check environment health before packaging
prometheus offline-doctor --format table

# Run full offline packaging
prometheus offline-package

# Enable auto-updates for this run
prometheus offline-package --auto-update --auto-update-max patch

# Run specific phases only
prometheus offline-package --only-phase dependencies --only-phase checksums
```

### Dependency management

```bash
# Check dependency status
prometheus deps status

# Plan upgrades
prometheus deps upgrade --sbom vendor/sbom.json

# Apply upgrades
prometheus deps upgrade --sbom vendor/sbom.json --apply --yes

# Validate against contract
prometheus deps guard

# Sync manifests from contract
prometheus deps sync --apply
```

All commands support `--help` for detailed options. See
`docs/packaging-workflow-integration.md` for complete workflow examples showing
how these commands work together for health checks, upgrades, and air-gapped
deployment preparation.

## Development practices

## CI/CD & Workflow Orchestration

Prometheus uses a coordinated set of GitHub workflows for continuous integration,
dependency management, and offline packaging. The pipeline architecture emphasizes:

- **Standardization**: Reusable composite actions reduce duplication
- **Air-gapped support**: Complete offline wheelhouse building  
- **Dependency safety**: Automated preflight checks and upgrade guards
- **Multi-platform**: Cross-platform wheel generation

### Key Workflows

- **CI** (`.github/workflows/ci.yml`): Build, test, package, and publish
- **Dependency Preflight** (`dependency-preflight.yml`): Validate dependency changes
- **Offline Packaging** (`offline-packaging-optimized.yml`): Multi-platform wheel building
- **Dependency Orchestration** (`dependency-orchestration.yml`): Coordinate all dependency operations
- **Pipeline Dry-Run** (`pipeline-dry-run.yml`): Test with fixtures and governance

### Reusable Actions

- `setup-python-poetry`: Standardized Python 3.12 and Poetry 1.8.3 installation
- `build-wheelhouse`: Consistent wheelhouse building with validation
- `verify-artifacts`: Artifact verification with offline doctor checks

See [docs/workflow-orchestration.md](docs/workflow-orchestration.md) for architecture details,
[docs/cross-workflow-integration.md](docs/cross-workflow-integration.md) for coordination patterns,
and [docs/new-workflow-checklist.md](docs/new-workflow-checklist.md) for adding new workflows.

## Development practices

- Keep modules self-contained and communicate via published events.
- When adding code, include unit tests inside the relevant stage and update
  cross-stage integration suites as needed.
- Record major design changes as ADRs in `docs/ADRs/` and link them from the
  affected documentation.
- Adhere to linting rules (80-character markdown lines, repository formatting
  configs) by running the local pre-commit hooks before opening a PR.
- Run `scripts/manage-deps.sh` (which invokes `scripts/preflight_deps.py`)
  whenever dependency pins change so `dist/requirements/` and
  `constraints/production.txt` stay in sync.
  macOS contributors can check for Finder artefacts with
  `scripts/check-macos-cruft.sh` before pushing.

For contribution details, see `docs/developer-experience.md` and the
`CONTRIBUTING.md` guide in `docs/`.
