# Quality Gates

Prometheus ships only when evidence-linked decisions, forecasts, and plans meet
the bars defined in `Promethus Brief.md`. Treat these gates as non-negotiable
for feature work, configuration changes, and releases.

## Verification layers

1. **Unit coverage.** Stage modules maintain ≥ 85% branch coverage and property
   checks for parsers, adapters, and policy rules.
   Pipeline bootstrap tests assert Temporal worker planning/runtime wiring
   so execution remains observable even in minimal deployments.
   
   **Validation:**
   ```bash
   pytest tests/unit/ --cov=. --cov-report=term-missing --cov-fail-under=85
   ```

2. **Stage integration.** Cross-stage tests replay golden event streams to
   verify schema compatibility and observability propagation.
   
   **Validation:**
   ```bash
   pytest tests/integration/ --cov=. --cov-report=term-missing
   ```

3. **End-to-end rehearsals.** Nightly pipelines ingest fixtures, run retrieval →
   reasoning → decision → execution flows, and compare outputs against approved
   baselines.
   
   **Validation:**
   ```bash
   pytest tests/e2e/ -m e2e --cov=. --cov-report=term-missing
   ```

4. **Chaos drills.** Inject degraded providers, stale caches, and slow plugins to
   validate fallbacks, retries, and circuit breakers.
   
   **Validation:**
   ```bash
   pytest tests/integration/ -m chaos
   ```

## Capability gates

- **Retrieval relevance.** Hybrid search must beat lexical-only baseline by
  ≥ 20% Recall@5 on representative corpora. Citation accuracy ≥ 95%—manual spot
  checks confirm claims match cited sources.
- **Reasoning groundedness.** Automated groundedness score ≥ 0.7 for 90% of
  evaluated answers; TruthfulQA or internal fact checks match top decile models.
  Final plans label assumptions when evidence is absent.
- **Decision explainability.** 95% of ledger entries include rationale,
  alternatives, evidence links, decision type, and next review date. Type 1
  decisions require dual approval.
- **Evidence & causality.** Each strategy outcome node holds ≥ 1 evidence link
  or explicit assumption justification; orphan nodes block promotion.
- **Forecasting calibration.** Brier score trends downward quarter over quarter
  relative to baseline; calibration error per probability bin ≤ 0.1.
- **Risk & assurance.** Simulated risk breaches trigger alerts ≥ 90% of the
  time; every high-priority risk lists owner and mitigation. Continuous
  assurance checks run without critical failures.
- **Metrics balance.** Scenario tests show no KPI optimisation causes catastrophic
  drops in paired counter-metrics beyond tolerance.
- **Security & privacy.** Zero open high-severity vulns at release, SBOM and
  Sigstore signatures verified, no PII in logs from integration tests, and
  right-to-be-forgotten flows pass automated checks.
- **Observability.** ≥ 95% of transactions emit complete traces ingestion →
  monitoring; SLO dashboards include exemplar traces for p99 degradation.
- **UX satisfaction.** Time-to-first-insight p95 < 60 s for standard document
  drops; accessibility audits report zero WCAG 2.1 AA blockers.

## Governance checkpoints

- Policy-as-code tests enforce RBAC, retention, and compliance rules.
- Manual reviews confirm risk officer sign-off for Type 1 decisions.
- Release PRs attach evaluation dashboards, risk assessments, and updated docs
  when public APIs change.

## Release gating flow

1. Link the change to an ADR or roadmap item; document impacted capabilities.
2. Attach unit, integration, lint, and evaluation artefacts to the PR.
3. Obtain approvals from module owner plus security and compliance delegates.
4. Tag release, sign artefacts, and record deployment metadata in the change
   log.
5. Monitor telemetry for 24 hours; trigger auto-rollback if SLO or policy
   budgets breach.

## Implementation Details

### Test Coverage Thresholds

- **Overall**: ≥ 80%
- **Critical Paths** (`common/contracts/`, `decision/`, `monitoring/`): ≥ 90%
- **Stage Services** (`ingestion/`, `retrieval/`, `reasoning/`, `execution/`): ≥ 85%
- **CLI and Utilities** (`prometheus/`, `chiron/`): ≥ 80%

### Configuration Validation

All configuration files must:
- Validate against schema
- Include default values for optional fields
- Document all required fields
- Support environment-specific overrides

**Policy Configuration**: `configs/defaults/policies.toml`
- Defines decision approval thresholds
- Specifies risk assessment rules
- Configures audit requirements
- Sets escalation policies

**Monitoring Configuration**: `configs/defaults/monitoring.toml`
- Defines metric collection intervals
- Configures collectors (Prometheus, OpenTelemetry)
- Sets alerting thresholds
- Defines SLOs and health checks

### CLI Integration Requirements

All CLI commands must:
- Execute without errors
- Provide comprehensive help text
- Handle errors gracefully
- Return appropriate exit codes
- Support --dry-run mode where applicable

**Validation:**
```bash
prometheus --help
prometheus pipeline --help
prometheus validate-config configs/defaults/pipeline.toml
prometheus deps status
```

### E2E Test Requirements

E2E tests must cover:
- Full pipeline execution (ingestion → monitoring)
- Policy enforcement scenarios
- Monitoring signal collection
- Configuration loading and validation
- CLI command integration
- Error handling and recovery

**Test Markers:**
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Long-running tests requiring infrastructure

## Standards mapping

- **ISO 9001:2015** → evidence completeness, decision auditability, calibration
  metrics.
- **NIST 800-137** → continuous monitoring, chaos drills, automated rollback
  gates.
- **GDPR / POPIA** → retention controls, subject deletion flows, access audits.
- **Sigstore / SBOM** → supply-chain integrity and artefact verification prior
  to promotion.
