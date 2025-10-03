# Copilot Instructions

## Big picture

- Prometheus is an event-driven strategy OS; every change flows through the six-stage pipeline: ingestion → retrieval → reasoning → decision → execution → monitoring (`README.md`, `docs/architecture.md`).
- Stages communicate via immutable events in `common/contracts/`; update contracts first, then stage `service.py`, tests, and docs.
- `Promethus Brief.md` plus `docs/ADRs/ADR-0001-initial-architecture.md` are the canon—stay aligned before shifting data shapes or behaviour.

## Architecture & stage map

- Each stage lives in its own folder with adapters, models, and tests; keep implementations local and document deltas in the stage README.
- Stage services (`<stage>/service.py`) own event handlers; avoid cross-stage imports outside published contracts.
- Core responsibilities: `ingestion/` connectors + PII scrub, `retrieval/` hybrid search, `reasoning/` orchestration, `decision/` policy ledger, `execution/` dispatchers, `monitoring/` telemetry loops.
- `api/` exposes the FastAPI surface, `prometheus/cli.py` offers the Typer CLI, `infra/` supplies docker-compose stacks for Postgres, OpenSearch, Qdrant, Temporal, and observability.
- Configuration defaults live under `configs/defaults/`; copy a profile and override rather than editing in place.

## Core workflows & commands

- `poetry install` to hydrate `.venv/`; activate when running scripts directly.
- Pipeline smoke test: `poetry run prometheus pipeline --config configs/defaults/pipeline_local.toml --query "configured"` (works without external services).
- Start the API: `poetry run prometheus-api` (override with `PROMETHEUS_CONFIG`).
- Lint/format gates: `poetry run ruff check`, `poetry run python scripts/format_yaml.py --all-tracked`, and `./.trunk/tools/trunk check` for actionlint + shellcheck parity with CI.
- Tests mirror the pipeline in `tests/`; target suites with `poetry run pytest tests/<stage>` plus cross-stage integration coverage when contracts shift.
- Dependency hygiene: `scripts/manage-deps.sh` (regenerates lockfile, exports, constraints, wheelhouse) and `scripts/deps-preflight.sh --check` for CI-style rehearsals.
- Offline + air-gapped: `poetry run prometheus offline-package` or `scripts/build-wheelhouse.sh` to refresh `vendor/wheelhouse/`; hydrate models with `python scripts/download_models.py`.
- YAML helper auto-formats and validates workflows; cache lives at `.cache/format_yaml_helper.json`, pass `--summary-path` or rely on `GITHUB_STEP_SUMMARY` in CI.

## Quality gates & conventions

- Pair feature work with stage-level unit tests and update cross-stage integration/e2e suites when contracts or events change.
- Instrument new paths with OpenTelemetry spans and ensure metrics land in `monitoring/` dashboards.
- CI expects SBOM publication, OSV/Scorecards scans, cosign signing, and clean Trunk lint; match those guardrails locally before pushing.
- Keep pipeline stages modular—prefer extending via plugins or adapters rather than cross-stage imports.

## Documentation & change management

- Update stage READMEs, `docs/overview.md`, and `docs/tech-stack.md` when behaviour or dependencies move; add/refresh ADRs for consequential decisions.
- Log recurring friction in `docs/pain-points.md` (use the provided template) whenever CI flakes repeat, manual steps recur, review comments repeat, or incidents land.
- When confidence drops below ~0.7, research authoritative sources, cite them, and summarise findings in PRs or `research_notes`.
- Contracts or API deltas require migration notes, regenerated SDK/tests, and roadmap updates if they shift commitments.

## Extending the system

- Prefer plugins in `plugins/` for optional capabilities; ship manifests, tests, and docs with the plugin.
- If a new stage or adapter is unavoidable, keep the event flow linear, add observability hooks, and land contract + service + doc updates together.
- Consolidate helper logic in `scripts/` or `common/helpers/` to avoid duplication; deprecate old paths and migrate call sites in the same patch.
