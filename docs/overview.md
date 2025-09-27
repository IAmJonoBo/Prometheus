# Overview

Prometheus is a strategy operating system that turns heterogeneous knowledge into
defensible, evidence-linked decisions. The product is OSS-first, modular, and
designed to run on anything from a single laptop to a full cluster while meeting
a "frontier-grade" bar across accuracy, latency, robustness, safety,
observability, security, and usability.

## Mission

- Automate the strategy lifecycle end-to-end without sacrificing explainability
  or auditability.
- Keep every recommendation grounded in cited evidence and explicit
  assumptions.
- Provide guardrails so irreversible decisions always trigger deeper review,
  while reversible decisions can flow quickly.
- Support organisations of any size through auto-configuration, optional
  plugins, and packaging choices (SaaS, on-prem, desktop, CLI, SDK).

## Success definition

Prometheus succeeds when:

- Decisions ship with transparent rationales, linked evidence, alternatives, and
  immutable ledger entries.
- Forecasting calibration (for example, Brier score) improves over time thanks to
  feedback loops.
- Users report faster time-to-insight and high confidence in system outputs.
- Quality gates block unsafe recommendations (no uncited claims, all compliance
  checks green) while maintaining fast UX.

## Capability stack

See `capability-map.md` for a full module-by-module responsibility matrix. At a
high level the pipeline flows as:

1. Ingestion → Normalise messy inputs, tag them, and keep provenance intact.
2. Retrieval → Index the knowledge base using hybrid lexical plus vector search
   with reranking and citation capture.
3. Reasoning → Orchestrate problem decomposition, critique loops, and tooling to
   surface assumptions and unknowns.
4. Decision → Classify decision criticality, enforce policy, log rationale,
   capture options, and route for approvals.
5. Execution → Translate accepted strategies into programs, initiatives, and
   deliverables; sync idempotently to external PM tools.
6. Monitoring → Track metrics, risks, and feedback to trigger adaptation loops
   and continuous learning.

Supporting capabilities include forecasting/simulation, causal modelling, risk &
assurance, collaboration, observability, security, accessibility, and
governance. Each capability exposes contracts so implementations can swap across
open-weight and provider APIs without vendor lock-in.
