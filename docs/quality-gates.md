# Quality Gates

Quality gates ensure Prometheus ships trustworthy decisions and retains audit
confidence. Contributors should treat this checklist as mandatory before
merging features or rolling out new configurations.

## Verification layers

1. **Unit coverage.** Every module exposes tests that prove contract compliance
   for parsers, adapters, and policy rules.
2. **Stage integration.** Cross-stage tests replay representative events to
   confirm schema compatibility and observability signal propagation.
3. **End-to-end rehearsals.** Nightly pipelines run golden scenarios from raw
   ingestion through execution and compare outputs against approved baselines.
4. **Chaos and failure drills.** Inject retries, degraded providers, and stale
   caches to validate resilience paths.

## Governance checkpoints

- **Evidence completeness.** Decision records must link to all cited sources and
  assumptions, with proofs stored in the ledger.
- **Policy compliance.** Automated checks enforce RBAC, retention, and sector
  regulations; failures block promotion until addressed.
- **Risk review.** High-impact decisions require dual approval and risk officer
  sign-off with mitigation plans documented.
- **Security review.** New dependencies undergo SBOM scanning, signature
  verification, and threat modelling updates.

## Metrics

Track these indicators inside the monitoring stack:

- Unit coverage (per stage) >= 85%.
- End-to-end scenario pass rate >= 98% over trailing 7 days.
- Mean time to detect regression < 15 minutes with automated alerting.
- Compliance drift (policy violations reopened) trending downward.

## Release gating flow

1. Open a change proposal referencing the relevant ADR or roadmap item.
2. Attach test run artefacts, evaluation dashboards, and risk assessments.
3. Obtain approvals from module owners plus security/compliance delegates.
4. Tag the release and record deployment metadata in the change log.
5. Monitor telemetry for 24 hours; roll back automatically if SLO errors breach
   tolerance.
