# Prometheus Roadmap

This roadmap mirrors the 0-30-60-90 plan defined in the canonical
`Promethus Brief.md`. Adjust timelines as we retire risks or uncover new
dependencies.

## 0-30 days — Minimum viable ingestion & QA

- Scaffold repo, CI, linting, and auto-benchmarking.
- Implement ingestion for core formats with provenance and masking.
- Deliver hybrid retrieval baseline (lexical first, vector optional) and a
  reasoning slice that answers questions with citations.
- Ship a lightweight analysis workspace UI and capture manual decision log
  entries.
- Establish the initial evaluation harness and nightly rehearsal pipeline.

## 30-60 days — Core modules & internal alpha

- Harden decision core with Type 1/Type 2 policies, alternatives, and ledger
  flows.
- Introduce the execution spine tree, initiative planning UI, and change
  history.
- Add authentication, roles, and collaboration basics (presence, comments).
- Integrate the model gateway with routing, telemetry, and fallback policies.
- Expand integration tests, load tests, and observability instrumentation.

## 60-90 days — Beta launch & hardening

- Finalise risk register UI, monitoring alerts, and accessibility audits.
- Implement security posture: SSO, RBAC enforcement, retention policies,
  encryption, SBOM, and signed artefacts.
- Polish UX (onboarding, empty states, streaming outputs) and improve
  performance to meet SLO targets.
- Package for SaaS and on-prem: container images, helm/compose, desktop
  installer, CLI.
- Run closed beta with target users; collect satisfaction, groundedness, and
  calibration metrics before GA planning.

## High-leverage open questions

- Will non-technical strategists trust AI suggestions, and how much transparency
  is required for adoption?
- Do open-weight LLMs deliver sufficient reasoning quality, or must we depend on
  proprietary providers for critical workflows?
- What hardware profile do target organisations possess, and how far can laptop
  mode scale before performance degrades?
- Which persona (strategist vs analyst) should UX optimise first for product
  fit?
- How essential are integrations with existing tooling (Excel, Jira, BI suites)
  for early adoption?
- Are customers constrained to on-prem deployments due to data governance, and
  how strict are localisation requirements?
- Will teams trust automated execution sync, or do they prefer manual review of
  generated work plans?
- How will evolving AI regulations (EU AI Act, etc.) classify the product, and
  what transparency controls must we prioritise?
- What appetite exists for community plugins, and what SDK support is required
  to foster contributions safely?
- Can the CRDT collaboration engine sustain large strategy docs without latency
  spikes, or do we need scoped locking as a fallback?

Revisit these questions at each milestone. Update this roadmap when answers
shift priorities, and record significant pivots in `docs/ADRs/`.
