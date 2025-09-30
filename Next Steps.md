# Next Steps

## Tasks
- [ ] Deliver Temporal worker implementations plus Prometheus/Grafana
   dashboards wired to OTLP exporters for end-to-end observability. *(Owner:
   Platform, Due: 2025-02-15)*
- [ ] Expose ingestion scheduler and PII masking metrics, validate
   configuration under load, and extend coverage with integration tests
   against live services. *(Owner: Data Pipeline, Due: 2025-01-31)*
- [x] Wire the retrieval regression harness into CI with seeded corpora and
  publish evaluation dashboards that gate releases (per-sample telemetry now
  emitted for debugging regressions). *(Owner: Retrieval, Due: 2025-02-07)*
- [ ] Implement real ingestion connectors and persistence for normalised
   documents.
- [ ] Extend retrieval adapters with hybrid search backends and reranking.
- [ ] Replace in-memory execution and monitoring shims with external system
   integrations and telemetry exporters.
- [ ] Rebuild wheelhouse for Python 3.13 with full main+extras coverage.
   *(Owner: Platform, Due: 2025-10-25)*
- [ ] Package pip-audit (or approved offline scanner) into wheelhouse and
   document usage. *(Owner: Security, Due: 2025-10-28)*

## Steps
- [x] Establish baseline test, lint, type-check, security, and build results
   for the current branch.
- [x] Instrument ingestion scheduler telemetry and redaction metrics,
   propagate them through monitoring signals, and document configuration
   validation behaviour.
- [x] Draft Temporal worker skeletons plus dashboard scaffolding once
   ingestion metrics land.
- [x] Automate retrieval regression harness execution in CI after
   observability enhancements ship.
- [x] Extend the regression harness to emit per-sample metrics and CLI
  telemetry for faster failure triage. *(Owner: Retrieval, Due: 2025-01-24)*
- [x] Harden wheelhouse packaging for cross-platform runners by adding Python
  interpreter auto-detection with explicit overrides.
- [x] Stabilise offline packaging CI workspace resets so `actions/checkout`
  retains a usable git directory on air-gapped runners.
- [ ] Regenerate offline wheelhouse artefacts for Python 3.13 and update the
  manifest/requirements snapshot before the next QA run.
- [ ] Package pip-audit (or approved offline scanner) and document execution
  flow for security gate parity.
- [ ] Exercise the Temporal worker plan and dashboard exports against a live
  stack to validate connectivity and schema compatibility.

## Deliverables
- Ingestion metrics surfaced via monitoring collectors and documented
   configuration validation guardrails.
- Temporal worker adapters and Grafana dashboards wired to OTLP exporters.
- CI job executing retrieval regression harness with published dashboards.
- Seeded regression dataset, CLI, and documentation for retrieval harness with
  per-sample JSON payloads.
- Offline bootstrap gap analysis with remediation plan for wheelhouse, QA, and
  security tooling.

## Quality Gates
- Tests: `pytest` green.
- Lint: `ruff check .` clean.
- Type-check: `pyright` with optional dependency suppressions or stubs; no
   blocking diagnostics.
- Security: `pip-audit` passes or has a documented network limitation.
- Build: `poetry build` succeeds.
- Coverage: ≥85% branch coverage on ingestion and monitoring modules (stretch
   until tooling lands).

## Links
- Current checks: pytest (`32103e`), ruff (`5f5dad`), pyright (`405e46`),
  pip-audit (command missing), poetry build (`0c79cb`).
- Offline bootstrap: `docs/offline-bootstrap-gap-analysis.md`.
- Harness sample telemetry coverage: `tests/unit/test_retrieval_evaluation.py`,
  `tests/unit/test_retrieval_regression_cli.py`.
- Regression harness automation: `.github/workflows/ci.yml`,
  `configs/defaults/retrieval_regression.toml`,
  `retrieval/regression_cli.py`, `tests/unit/test_retrieval_evaluation.py`.

## Risks / Notes
- Optional dependencies (`temporalio`, `opentelemetry`, `qdrant`,
   `sentence-transformers`) are not installed in CI images; type-checking
   emits missing import diagnostics until stubs or conditionals are added.
- `pip-audit` currently unavailable because dependency resolution against
  `pypi.org` is blocked in the offline environment; rerun once connectivity or
  mirror caching is available.
- Retrieval harness requires seeded corpora and evaluation dashboard stack;
   scoping is ongoing.
- Coverage currently 84% (target ≥85%); additional ingestion and monitoring
  tests needed to raise the baseline.
- Baseline QA commands require wheelhouse refresh; pytest and poetry build
  run, but ruff and pyright fail due to missing dependencies bundled in the
  offline artefacts.
- Wheelhouse currently only holds metadata files; numpy wheel missing for
  Python 3.13 prevents bootstrap install.
- Security gate (`pip-audit`) is blocked until the binary is packaged or an
  approved offline scanner is provided.
