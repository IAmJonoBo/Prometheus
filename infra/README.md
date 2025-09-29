# Local infrastructure stack

This directory contains docker-compose definitions for the external services
referenced throughout the Prometheus tech stack. The goal is to provide an
opt-in baseline so developers can quickly launch dependencies without wiring
production tooling.

## Services

- **Postgres** — system of record at
  `postgres://prometheus:changeme@localhost:5432/prometheus`.
- **Redis** — queue/cache shim at `redis://localhost:6379` for Temporal tasks
  or rate limiting.
- **NATS** — lightweight event bus at `nats://localhost:4222` (UI on
  `http://localhost:8222`).
- **OpenSearch** — lexical/BM25 search at `http://localhost:9200`.
- **Qdrant** — dense vector retrieval at `http://localhost:6333`.
- **Temporal** — workflow engine (gRPC `localhost:7233`, UI
  `http://localhost:8080`).
- **OpenFGA** — relationship-based authorisation playground at
  `http://localhost:8082/playground`.
- **Keycloak** — identity provider at `http://localhost:8081` (admin/admin).
- **Vault** — secrets broker in dev mode at `http://localhost:8200`
  (root/root).
- **Prometheus** — metrics collection at `http://localhost:9090`.
- **Alertmanager** — alert routing at `http://localhost:9093`.
- **Grafana** — dashboards at `http://localhost:3000` (admin/admin).
- **Loki** — log aggregation at `http://localhost:3100`.
- **Tempo** — trace storage at `http://localhost:3200`.
- **OTel Collector** — receives OTLP traffic on gRPC `4317` / HTTP `4318` and
  forwards to Tempo, Loki, and Prometheus.
- **Langfuse** — LLM observability UI at `http://localhost:3001` (set
  `LANGFUSE_DATABASE_URL` before launching).
- **Phoenix** — Arize Phoenix UI for LLM evaluations at
  `http://localhost:6006`.
- **OPA** — policy engine API at `http://localhost:8181` serving sample Rego
  policies from `opa/policies/`.
- **Flipt** — feature flag service at `http://localhost:8083`.
- **OpenCost** — cost monitoring API at `http://localhost:9095` (pulls from the
  Prometheus scraper). The compose file references the upstream GHCR image;
  run `docker login ghcr.io` with the appropriate token before launching if
  your environment cannot pull public GHCR images anonymously.

> **Note:** The stack disables security for OpenSearch and uses the Temporal
> auto-setup image. Do not run this compose file in production.

## Prerequisites

- Docker Engine 24+
- Docker Compose v2
- At least 12 GB of free memory for the full stack (search + observability
  components are memory hungry).

## Usage

Launch all services:

```bash
cd infra
docker compose up -d
```

Tear down the stack (volumes are preserved unless removed):

```bash
docker compose down
```

To reclaim disk space, remove volumes:

```bash
docker compose down --volumes
```

### Environment configuration

- `infra/.env` holds development defaults for Postgres and Langfuse. Override
  any value by editing the file locally or by exporting the variable in your
  shell before running `docker compose`.
- `LANGFUSE_DATABASE_URL` defaults to the shared Postgres instance for
  convenience. Point it at an external database when testing migrations or
  multi-tenant setups.
- The Postgres password ships as `changeme`. Set a stronger secret when you
  expose the stack beyond localhost.

## Prometheus & Alertmanager configuration

`prometheus/prometheus.yml` scrapes the API service on port `8000` by default.
Set `API_METRICS_HOST` when running outside Docker to expose the correct
hostname or adjust the scrape target directly.

`alertmanager/alertmanager.yml` wires a default noop receiver. Replace this
with Slack, PagerDuty, or email routes as your policies evolve.

## Temporal dynamic configuration

The `temporal` folder mirrors the structure expected by the Temporal auto-setup
image. Update `dynamicconfig/development.yaml` when tuning worker-specific
betas or enabling rate-limiting features during development.

## Observability pipeline

- `loki/local-config.yaml` configures filesystem storage and points rule
  evaluations at Alertmanager.
- `tempo/config.yaml` accepts OTLP traces and stores them locally.
- `otel-collector/config.yaml` fans OTLP traffic out to Tempo, Loki, and the
  Prometheus remote write endpoint. Point your services at
  `http://localhost:4318` for HTTP OTLP ingestion.
- `opa/policies/` contains placeholder Rego modules. Replace `example.rego`
  with policies that match your governance requirements.

## Identity & policy

- `keycloak/realm-export.json` seeds a local realm with an admin user and a
  sample `dev-user` account so that API experiments can rely on OIDC flows.
- OpenFGA runs with an in-memory playground enabled; load the default
  storefront model or author your own in the UI.
- Vault boots in dev mode with the root token `root`. Do **not** reuse this
  setup outside local development.
