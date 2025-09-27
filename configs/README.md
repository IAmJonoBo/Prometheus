# Configs

This directory holds configuration templates and documentation for every
deployment profile described in the `Promethus Brief.md`.

## Configuration layers

1. **Defaults (`configs/defaults/`).** Baseline settings shared across laptop,
   self-hosted, and SaaS deployments. `pipeline.toml` captures the bootstrap
   pipeline wiring used by the CLI entrypoint.
2. **Environment overrides (`configs/env/`).** Per-environment values (dev,
   staging, prod) that tune feature flags, SLO thresholds, and telemetry sinks.
3. **Secrets (`.env`, secret managers).** API keys, credentials, and signing
   material; never commit secrets to the repo. Reference them through
   environment variables documented in `.env.example`.
4. **Plugin manifests.** Optional extensions declare required configuration and
   permissions; keep manifests colocated with each plugin and document any new
   keys here.

## Packaging profiles

- **Laptop / desktop:** Use `.env.local` to specify lightweight model paths,
  local storage directories, and disable heavy telemetry exporters.
- **Self-hosted server:** Configure queue backends, distributed cache
  addresses, certificate locations, and logging destinations. Enforce
  per-tenant encryption keys and RBAC scopes via environment variables.
- **SaaS multi-tenant:** Store secrets in the cloud provider’s key vault,
  enable feature flag backends, and set rollout/canary percentages.
  Provide automation for rotation of signing keys and SBOM artefacts.
- **CLI / SDK:** Expose minimal configuration (API base URL, auth token)
  so scripting clients can interact with staging or production clusters.

## Operational guidance

- Keep configuration files under source control except for secrets.
- Document any new setting in this README, including acceptable ranges and
  its impact on quality gates or SLOs.
- Provide migration notes when renaming or removing settings; update
  `docs/developer-experience.md` and relevant stage READMEs accordingly.
- Add validation hooks (TBD) that lint configuration values during CI and
  pre-flight checks before deployment.

## Backlog

- Add `.env.example` templates covering pipeline stages, model gateway, and
  telemetry sinks.
- Document integration-specific configuration (e.g., Jira, Slack, email).
- Script configuration diff tooling to highlight unsafe changes before rollout.
