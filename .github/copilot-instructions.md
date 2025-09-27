# Copilot Instructions

## Quick orientation

- Prometheus is an event-driven strategy OS for evidence-linked decision
  automation.
- The repo is a scaffolded monorepo: each top-level directory mirrors a
  pipeline stage or cross-cutting concern.
- Treat `Promethus Brief.md` as the canonical product narrative; keep all other
  docs aligned with it.
- Start by reading the relevant stage README plus
  `docs/ADRs/ADR-0001-initial-architecture.md` to align with accepted
  decisions.

## Architecture & flow

- Core pipeline order: ingestion → retrieval → reasoning → decision → execution
  → monitoring (`README.md`).
- Stages communicate via structured events; avoid leaking stage-specific
  types—place shared contracts in `common/`.
- Each stage folder should stay self-contained so it can scale to separate
  services if needed.
- Stage services live in `<stage>/service.py`; keep handler interfaces aligned
  with the contracts in `common/contracts`.

## Module responsibilities

- `ingestion/`: connectors, schedulers, and normalization of raw sources.
- `retrieval/`: hybrid lexical/vector retrieval and reranking strategies.
- `reasoning/`: model orchestration and evidence synthesis.
- `decision/`: policy evaluation, scoring, and guardrails.
- `execution/`: action dispatchers, webhooks, or RPA integrations.
- `monitoring/`: logging, metrics, feedback loops, and incident hooks.
- `ux/`: collaboration UI, CRDT sync, and WCAG 2.1 AA accessibility work.
- `plugins/`: optional extensions; enforce isolation and auto-configuration per
  plugin.
- `common/contracts/`: shared dataclasses that formalize event payloads between
  stages; update these first when interfaces move.

## Configuration & environments

- Keep environment and deployment configuration in `configs/`; document
  defaults and secrets handling there.
- When adding external dependencies, note hardware or model assumptions inside
  the relevant plugin or config README.
- Use `scripts/benchmark-env.sh` to sanity-check local hardware assumptions
  before recommending high-end defaults.

## Quality & testing

- Mirror pipeline stages inside `tests/`; pair each feature with unit tests plus
  cross-stage integration coverage.
- Add new quality gates or security controls to `docs/ROADMAP.md` and
  reference them from test plans.
- Security expectations include SSO, RBAC, encryption, and supply-chain
  hygiene (see `README.md` and ADR-0001).

## Documentation workflow

- Start with `docs/README.md` for navigation; sync updates across the topic
  guides (`overview.md`, `architecture.md`, `model-strategy.md`,
  `quality-gates.md`, `performance.md`, `ux.md`, `developer-experience.md`,
  `tech-stack.md`).
- Record architecture changes as new ADRs alongside `ADR-0001`; link them from
  affected READMEs and the relevant topic guide.
- Update per-stage READMEs with interface contracts, event schemas, and
  dependency notes whenever APIs change.
- Reflect roadmap or risk changes in `docs/ROADMAP.md`; retire obsolete docs as
  part of the PR if content migrates elsewhere.
- Any net-new decision logic, tooling, or SLO commitments must also be mirrored
  back into `Promethus Brief.md`.

## Style & lint

- Markdown enforces the 80-character rule; wrap paragraphs and lists
  accordingly.
- Prefer spaces over tabs and keep tables narrow enough to satisfy the linter;
  use subsection lists when tables would exceed the width limit.
- Run the configured Trunk checks (`trunk check`), which wrap markdownlint,
  ruff, shellcheck, and formatter rules used in CI, before opening a PR.

## When extending the system

- Prefer adding capabilities as plugins when they do not belong to a core stage.
- For new pipeline stages, explain the rationale in an ADR and ensure the event
  flow remains linear and traceable.
- Surface observability hooks in `monitoring/` alongside any new action or
  decision logic to maintain feedback loops.
- When touching stage services, keep the corresponding contract changes,
  service handler updates, and docs PR-ready in one patch set.
