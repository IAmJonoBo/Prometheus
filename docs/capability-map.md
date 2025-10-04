# Capability Map

This map summarises the core modules and supporting capabilities described in
the Promethus Brief. Use it to confirm ownership when adding features or
plugins.

## Core pipeline

### Ingestion & Normalisation

- Parse heterogeneous sources (documents, spreadsheets, web pages, APIs).
- Clean and tag data while preserving provenance and handling PII safely.
- Output normalised text and structured records in staging with source IDs.

### Retrieval & Knowledge Store

- Maintain hybrid lexical plus vector indexes with reranking for relevance.
- Support multilingual and long-context retrieval with citation metadata.
- Serve ranked passages with access-aware filtering back to reasoning.

### Reasoning & Synthesis

- Decompose problems into tool calls, critique loops, and red/green teaming.
- Surface explicit assumptions, unknowns, and confidence notes in outputs.
- Produce drafts, analyses, and Q&A responses grounded in cited evidence.

### Decision Core & Ledger

- Classify decision criticality (Type 1 vs Type 2) and enforce approval rules.
- Capture alternatives, rationale, evidence links, and status transitions.
- Emit structured ledger entries, alerts, and review reminders.

### Execution Spine

- Map strategy → program → initiative → tactic → deliverable hierarchies.
- Sync plans idempotently to external PM tools and propagate schedule impacts.
- Maintain change history and link work items back to strategic intent.

### Monitoring & Adaptation

- Define leading and lagging indicators with anti-gaming guardrails.
- Track risks, telemetry, and thresholds to trigger alerts or re-planning.
- Feed outcomes back into reasoning for continuous learning.

## Supporting capabilities

### Evidence & Causality

- Build theories of change that tie activities to outcomes and assumptions.
- Store causal graphs with justification notes and linked metrics.

### Forecasting & Simulation

- Deliver probabilistic forecasts, scenario comparisons, and Brier tracking.
- Support interactive what-if analysis tied to strategic assumptions.

### Risk & Assurance

- Maintain risk registers with owners, mitigations, and tolerance bands.
- Integrate continuous assurance checks plus audit-ready reports.

### Collaboration & Knowledge Management

- Provide CRDT-backed co-editing, commenting, and access control layers.
- Preserve audit trails and notifications for concurrent edits.

### Observability & Logging

- Instrument metrics, traces, logs, and cost/latency tracking per module.
- Capture exemplars for slow paths and surface SLO compliance dashboards.

### Security & Privacy

- Enforce SSO, RBAC, encryption, PII detection, SBOM tracking, and signing.
- Record security-sensitive actions for later audits and compliance proofs.

### Accessibility & Internationalisation

- Meet WCAG 2.1 AA across UI flows and support localisation-ready content.
- Allow keyboard-only usage and multi-language report generation.

### Governance & Policy

- Express policy-as-code to block non-compliant actions automatically.
- Track lineage, retention, and compliance evidence for regulated deployments.
