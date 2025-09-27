# User Experience

Prometheus designs every interaction around explainable, collaborative
decision-making. The experience mirrors the flows captured in `Promethus
Brief.md` while guaranteeing accessibility, transparency, and user control.

## Core journeys

1. **Document drop → Defensible brief.** Users ingest files on an ingestion
   dashboard, watch progress indicators, and pivot into the analysis workspace
   where AI-drafted briefs include inline citations, expandable details, and
   "Explain" buttons that surface reasoning steps and assumptions.
2. **Hypothesis → Evidence & causal plan.** In the strategy canvas users state
   hypotheses, accept suggested evidence, and assemble theory-of-change graphs
   through a visual causal builder or guided questionnaire, before generating
   initiative plans tied to metrics.
3. **Options → Decision record.** A wizard captures context, generates option
   cards, scores criteria, and produces a recommendation with rationale and
   alternative analysis before writing to the decision ledger with approvals.
4. **Plan → Execution sync.** The execution dashboard exposes the
   program→initiative→tactic tree, surfaces risk/metric status, and performs
   idempotent exports to PM tools with diff previews and live status updates.

## Design principles

- **Progressive disclosure.** Default views emphasise concise summaries; users
  expand to reveal evidence, assumptions, or full chain-of-thought when needed.
- **Assistive guidance.** Wizards, templates, and contextual prompts steer
  novices through complex workflows without blocking expert shortcuts.
- **Explainability everywhere.** Every AI suggestion exposes citations,
  confidence cues, and rationale summaries; users can request deeper dives.
- **Delight with control.** Real-time collaboration shows presence, colour-coded
  edits, and audit trails; annotations and comments integrate with the ledger.

## Accessibility & internationalisation

- Meet WCAG 2.1 AA: semantic HTML, high contrast, focus indicators, and screen
  reader labels verified with automated and manual audits.
- Provide full keyboard navigation for ingestion, analysis, approvals, and plan
  edits; document shortcuts for power users.
- Localise UI strings, dates, and number formats; support multi-language report
  generation and display locale-specific compliance notices.

## Collaboration system

- CRDT-backed editing keeps content conflict-free offline or during concurrent
  sessions, with activity feeds summarising changes since last visit.
- Inline comments, suggestion mode, and decision-linked threads maintain context
  and tie back to ledger entries.
- Notification settings let users subscribe to initiatives, risks, metrics, or
  specific decisions with batched digests to avoid fatigue.

## UI building blocks

- **Home dashboard:** recent activity, "Ask a question" entry point, system
  status, and onboarding tips.
- **Document library:** tag-aware explorer with ingestion progress, provenance,
  and retention badges.
- **Analysis workspace:** two-pane layout combining prompt history and AI output
  with citation side panels and feedback controls.
- **Strategy editor:** outline-driven editor with initiative tree, metric cards,
  and causal model overlay.
- **Decision log:** filterable table with detailed ledger pages, comparison of
  superseded decisions, and export actions.
- **Metrics & risk dashboards:** emoji-free heatmaps, threshold alerts, and
  drill-down views linked to initiatives and owners.

## Feedback loops

- Capture post-decision satisfaction scores and free-text feedback; route into
  backlog triage with traceability to affected journey.
- Highlight UX debt in `docs/ROADMAP.md` and prioritise when accessibility or
  usability gates flag regressions.
- Replay anonymised interaction traces during design reviews to refine flows
  without exposing sensitive content.
