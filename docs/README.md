# Docs

Prometheus is an OSS-first, event-driven strategy OS for evidence-linked decision
automation. These docs capture the product brief, architecture choices, quality
bars, and daily workflows so contributors can extend the system without
re-reading the entire strategy document.

## How this folder is organized

- `overview.md` &mdash; Executive summary, product goals, and the capability stack
  distilled from the Promethus Brief.
- `capability-map.md` &mdash; Responsibility matrix for each pipeline module and
  supporting capability.
- `architecture.md` &mdash; Data/control flow, plugin isolation model, and example
  walkthroughs.
- `model-strategy.md` &mdash; Unified model gateway design, provider routing, and
  safety policies.
- `quality-gates.md` &mdash; Verification criteria, metrics, and governance
  expectations.
- `performance.md` &mdash; Target SLOs, scaling guidance, and cost management
  tactics.
- `ux.md` &mdash; Core user journeys, design principles, and accessibility
  requirements.
- `developer-experience.md` &mdash; Repo structure, testing strategy, CI/CD, and
  contribution standards.
- `tech-stack.md` &mdash; OSS-first stack, tooling, and deployment profiles that
  map the brief to concrete components.
- `offline-packaging-status.md` &mdash; Latest dependency drift snapshots and
  remediation workflow for offline artefacts.
- `ROADMAP.md` &mdash; Milestones and open questions (kept in sync as features
  land).
- `ADRs/` &mdash; Architecture decision records; add a new ADR for any structural
  change.

Start with `overview.md` for the big picture, then drill into the relevant
topic. Each guide surfaces actionable checklists and links into stage-specific
READMEs in the repo (e.g., `ingestion/README.md`) to keep implementation
details close to code.
