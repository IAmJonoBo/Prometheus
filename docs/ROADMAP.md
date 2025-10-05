# Prometheus Roadmap

This roadmap mirrors the 0-30-60-90 plan defined in the canonical
`Promethus Brief.md`. Current status reflects actual implementation progress
as of January 2025. Adjust timelines as we retire risks or uncover new
dependencies.

## 0-30 days — Minimum viable ingestion & QA

**Status: 🚧 Partially Complete**

- ✅ Scaffold repo, CI, linting, and auto-benchmarking - *CI operational, quality gates in place*
- ✅ Implement ingestion for core formats with provenance and masking - *Basic web extraction + PII guards working*
- 🚧 Deliver hybrid retrieval baseline (lexical first, vector optional) - *RapidFuzz lexical working, semantic search in development*
- 🚧 Reasoning slice that answers questions with citations - *Event propagation working, LLM orchestration pending*
- 🚧 Ship a lightweight analysis workspace UI - *CLI operational, web UI is placeholder only*
- 🚧 Capture manual decision log entries - *Audit trail functional, rich workflows pending*
- ✅ Establish the initial evaluation harness - *RAG evaluation framework in place*
- 🚧 Nightly rehearsal pipeline - *CI tests running, continuous monitoring setup incomplete*

## 30-60 days — Core modules & internal alpha

**Status: 🚧 In Development**

- 🚧 Harden decision core with Type 1/Type 2 policies - *Policy stub exists, rich engine in development*
- 🚧 Alternatives and ledger flows - *Basic audit trail, advanced workflows not started*
- 📋 Introduce execution spine tree - *Dispatcher skeleton exists, Temporal workers not production-ready*
- 📋 Initiative planning UI - *Not started, CLI-only currently*
- 📋 Change history tracking - *Basic audit, no UI or rich query support*
- 📋 Authentication, roles, collaboration basics - *Not implemented, single-user mode only*
- 📋 Presence, comments - *Planned for future, no CRDT implementation yet*
- 🚧 Model gateway with routing, telemetry, fallback policies - *Telemetry in place, routing/fallback incomplete*
- 🚧 Integration tests, load tests - *E2E test suite exists, load testing not started*
- ✅ Observability instrumentation - *OpenTelemetry traces, Prometheus metrics operational*

## 60-90 days — Beta launch & hardening

**Status: 📋 Planned**

- 📋 Finalise risk register UI - *Not started, no UI components built*
- 🚧 Monitoring alerts - *Alerting config exists, Grafana dashboards in development*
- 📋 Accessibility audits - *Not started, web UI incomplete*
- 📋 Security posture: SSO, RBAC enforcement - *Authentication not implemented*
- 🚧 Retention policies, encryption - *Basic patterns, production implementation pending*
- ✅ SBOM and signed artefacts - *SBOM generation operational, signing workflows in place*
- 📋 Polish UX (onboarding, empty states, streaming outputs) - *CLI functional, web UI incomplete*
- 📋 Performance to meet SLO targets - *SLO definitions exist, optimization not started*
- 🚧 Package for SaaS and on-prem - *Docker compose working, Helm charts not started*
- 🚧 Container images - *Development images exist, production hardening pending*
- 📋 Desktop installer - *Tauri skeleton exists, no builds yet*
- ✅ CLI - *Fully operational with Chiron subsystem*
- 📋 Closed beta with target users - *Not started, requires stable features first*

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

## Status Legend

- ✅ **Complete** - Feature implemented and operational
- 🚧 **In Progress** - Active development, partially working
- 📋 **Planned** - Not started, future work
- ⚠️ **Blocked** - Dependencies or decisions needed
