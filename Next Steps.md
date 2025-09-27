# Next Steps

## Tasks
- [ ] Deliver Temporal worker implementations plus Prometheus/Grafana dashboards wired to OTLP exporters for end-to-end observability. *(Owner: Platform, Due: 2025-02-15)*
- [ ] Expose ingestion scheduler and PII masking metrics, validate configuration on load, and extend coverage with integration tests hitting live services. *(Owner: Data Pipeline, Due: 2025-01-31)*
- [ ] Wire the retrieval regression harness into CI with seeded corpora and publish evaluation dashboards that gate releases. *(Owner: Retrieval, Due: 2025-02-07)*

## Steps
- [x] Establish baseline test, lint, type-check, security, and build results for the current branch.
- [x] Instrument ingestion scheduler telemetry and redaction metrics, propagate them through monitoring signals, and document configuration validation behavior.
- [ ] Draft Temporal worker skeletons plus dashboard scaffolding once ingestion metrics land.
- [ ] Automate retrieval regression harness execution in CI after observability enhancements ship.

## Deliverables
- Ingestion metrics surfaced via monitoring collectors and documented configuration validation guardrails.
- Temporal worker adapters and Grafana dashboards wired to OTLP exporters.
- CI job executing retrieval regression harness with published dashboards.

## Quality Gates
- Tests: `pytest` green.
- Lint: `ruff check .` clean.
- Type-check: `pyright` with optional dependency suppressions or stubs, no blocking diagnostics.
- Security: `pip-audit` passes or documented network limitation.
- Build: `poetry build` succeeds.
- Coverage: ≥85% branch coverage on ingestion and monitoring modules (stretch until tooling lands).

## Links
- Current checks: pytest (`877739`), ruff (`249f4a`), pyright (`7680be`), pip-audit (`4c1022`), poetry build (`023e7b`).

## Risks / Notes
- Optional dependencies (temporalio, opentelemetry, qdrant, sentence-transformers) are not installed in CI images; type-checking emits missing import diagnostics until stubs or conditionals are added.
- pip-audit currently fails due to SSL verification against pypi.org; re-run once certificates are available.
- Retrieval harness requires seeded corpora and evaluation dashboard stack; scoping ongoing.
