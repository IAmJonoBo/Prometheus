# Developer Experience

This guide helps contributors stay productive while maintaining the high bars
for safety and quality outlined across the docs set.

## Repo structure refresher

- `ingestion/` through `monitoring/` mirror the pipeline; keep integrations and
  tests scoped to their stage.
- `common/` contains shared contracts, data models, and utilities. Avoid
  circular dependencies by rooting abstractions here.
- `plugins/` host optional extensions. Treat each plugin as an independently
  deployable package with its own README.
- `tests/` mirrors the pipeline for unit plus integration suites.

## Tooling

- Use `ruff` and markdown lint configs (MD013 off) to ensure formatting
  consistency. Obey the 80-character line rule in this repo.
- Preferred package managers: `poetry` for Python services, `pnpm` for frontend
  assets, and `uv` for fast virtualenv management.
- Run `pre-commit` hooks locally; they mirror CI checks for lint, type, and
  security scans.

## CI/CD flow

1. Open a PR with linked roadmap item or ADR reference.
2. GitHub Actions run lint, tests, security scans, and build artefacts.
3. Upon approval, merges trigger packaging pipelines and optional canary deploys
   into staging environments.
4. Release notes update automatically from conventional commits; verify the log
   before tagging.

## Local development

- Seed the system with example events via `tests/fixtures/` when writing new
  features.
- Use docker-compose profiles (coming soon) to stand up minimal dependencies
  such as vector stores and tracing backends.
- Follow the documented env var contracts in `configs/README.md` when adding new
  secrets or feature flags.

## Knowledge sharing

- Update stage-specific READMEs whenever APIs change; include sample payloads.
- Capture significant architecture shifts as ADRs to keep history searchable.
- Record demos and attach them to the monitoring feedback loop so operational
  teams can learn new workflows quickly.
