# Prometheus Documentation Handbook

Prometheus is an OSS-first, event-driven strategy OS for evidence-linked
decision automation. This directory gathers the product narrative, technical
architecture, operational runbooks, and roadmap so contributors can find the
right level of depth without chasing scattered notes.

## 🚀 Quick Start

**New to Prometheus?**

1. 📊 [Current Status](../CURRENT_STATUS.md) - What works today, what's in progress
2. 📋 [Project Roadmap](ROADMAP.md) - Near-term committed work
3. 🎯 [Future Enhancements](../FUTURE_ENHANCEMENTS.md) - Long-term vision
4. 📖 [Overview](overview.md) - Executive summary and product goals
5. 🏗️ [Architecture](architecture.md) - System design and event flows

**Contributing?**

- 🚀 [Getting Started](getting-started.md) - Setup guide (15-20 minutes)
- ✅ [Onboarding Checklist](ONBOARDING_CHECKLIST.md) - First contribution guide (30-45 minutes)
- 📝 [Contributing Guide](CONTRIBUTING.md) - How to contribute
- 🔧 [Developer Experience](developer-experience.md) - Conventions and workflows
- 🧪 [Testing Strategy](TESTING_STRATEGY.md) - Comprehensive testing guide
- 📦 [Module Index](MODULE_INDEX.md) - All modules and their documentation
- 🐛 [TODO Refactoring](../TODO-refactoring.md) - Open tasks and technical debt

---

Use the sections below to navigate the canonical guides. Topic handbooks link
directly to code, contracts, and workflows so architecture stays aligned with
delivery.

## Orientation

- `overview.md` — Executive summary, product goals, and system promises drawn
  from the Prometheus Brief.
- `capability-map.md` — Capability matrix showing which pipeline stage owns
  ingestion, reasoning, execution, monitoring, and supporting functions.
- `architecture.md` & `solution-architecture.md` — Control flow, plugin
  isolation, deployment topology, and representative event journeys.
- `tech-stack.md` & `model-strategy.md` — Platform stack, provider strategy,
  and safety guardrails for model orchestration.
- `module-boundaries.md` — Boundaries and extension points for each stage.

## Chiron Subsystem (Developer Tooling)

- `chiron/README.md` — Comprehensive guide to the Chiron subsystem for packaging,
  dependency management, and developer tooling.
- `chiron/QUICK_REFERENCE.md` — Quick reference for common Chiron commands and workflows.
- `packaging-workflow-integration.md` — Detailed packaging workflows.
- `cibuildwheel-integration.md` — Multi-platform wheel building with CI/CD.

## Delivery & Engineering

- `developer-experience.md` — Repository conventions, testing strategy, and
  CI/CD expectations.
- `performance.md` — Service-level objectives, scaling guidance, and cost
  management tactics.
- `quality-gates.md` — Verification criteria and governance checks enforced in
  CI and release workflows.
- `refactoring-summary.md` & `dependency-graph.md` — Current refactor plan and
  module dependency visuals.

## Dependency & Packaging Platform

- `dependency-governance.md` — Canonical handbook for policy, guard analysis,
  upgrade planning, runbooks, and the forward-looking backlog.
- `dependency-graph.md` — Module dependency visualization
- `packaging-workflow-integration.md` — Deep dive into the unified CLI
  experience across doctor, package, and dependency commands.
- `offline-packaging-orchestrator.md` — Phase-by-phase walkthrough of the
  wheelhouse and model packaging orchestrator.
- `offline-contingency.md` — Playbook for operating without internet access or
  when Git LFS mirrors are unavailable.

**Archived/Superseded**: See `archive/` for historical dependency tracking docs.

## Continuous Delivery & Automation

- `ci-handbook.md` — Consolidated CI reference covering workflow improvements,
  packaging automation, artifact validation, and troubleshooting.
- `CI/README.md` — In-depth workflow, caching, and job-by-job expectations for
  the Actions stack.

## Observability & Operations

- `observability.md` — Telemetry surface, dashboards, and alert routing.
- `pain-points.md` — Running log of operational friction and mitigation ideas.
  (See the CI handbook for packaging and CLI integration details.)

## Governance, Roadmap, and Community

- `ROADMAP.md` — Milestones, sequencing, and open questions through upcoming
  releases.
- `upgrade-guard.md` — Contract enforcement policies and risk scoring model.
- `governance/` — Audit, lineage, and reporting scaffolding.
- `CODE_OF_CONDUCT.md` & `CONTRIBUTING.md` — Community guidelines and
  contribution process.
- `ADRs/` — Architecture decision records; add one for any structural change.

## Reference & Samples

- `samples/` — Representative configuration profiles, manifests, and data
  bundles for experimentation.
- `CLI_UPGRADE_SUMMARY.md` — Release notes for CLI usability improvements.

## Archive

- `archive/` — Legacy and superseded documentation retained for historical
  reference. See [archive/README.md](archive/README.md) for details.

---

Start with `overview.md` for the big picture, then jump into the handbook that
matches your workstream. Stage-level READMEs (for example,
`ingestion/README.md`) stay co-located with the implementation, while this
directory documents the cross-stage narratives and operational playbooks.
