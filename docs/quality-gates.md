# Quality Gates

Prometheus ships only when evidence-linked decisions, forecasts, and plans meet
the bars defined in `Promethus Brief.md`. Treat these gates as non-negotiable
for feature work, configuration changes, and releases.

## Verification layers

1. **Unit coverage.** Stage modules maintain ≥ 85% branch coverage and property
   checks for parsers, adapters, and policy rules.
   Pipeline bootstrap tests assert Temporal worker planning/runtime wiring
   so execution remains observable even in minimal deployments.
2. **Stage integration.** Cross-stage tests replay golden event streams to
   verify schema compatibility and observability propagation.
3. **End-to-end rehearsals.** Nightly pipelines ingest fixtures, run retrieval →
   reasoning → decision → execution flows, and compare outputs against approved
   baselines.
4. **Chaos drills.** Inject degraded providers, stale caches, and slow plugins to
   validate fallbacks, retries, and circuit breakers.

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

## Standards mapping

- **ISO 9001:2015** → evidence completeness, decision auditability, calibration
  metrics.
- **NIST 800-137** → continuous monitoring, chaos drills, automated rollback
  gates.
- **GDPR / POPIA** → retention controls, subject deletion flows, access audits.
- **Sigstore / SBOM** → supply-chain integrity and artefact verification prior
  to promotion.
