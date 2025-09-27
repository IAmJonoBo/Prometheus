# Architecture

Prometheus follows a linear event-driven pipeline so every contribution stays
traceable. Each stage consumes a typed event, augments it, and forwards the
result. Shared contracts live in `common/` so that the stages can scale out as
independent services without leaking implementation details.

## Principles

- **Evidence first.** Every action keeps source IDs and citations attached so a
  reviewer can walk the decision path later.
- **Loose coupling.** Modules communicate via immutable events and avoid direct
  service calls. This allows horizontal scaling and replay for audits.
- **OSS-friendly.** Adapters, models, and plugins favour open offerings with
  clear fallbacks to proprietary options if required by policy.
- **Observability by design.** Metrics, traces, and logs ship alongside every
  event to feed the monitoring stage and external telemetry platforms.

## Pipeline flow

1. **Ingestion.** Connectors pull or receive content, normalise formats, scrub
   PII, and attach provenance metadata.
2. **Retrieval.** Hybrid lexical/vector stores resolve the current question into
   scored passages and structured facts with access-aware filtering.
3. **Reasoning.** Orchestrators break work into tool calls, critique loops, and
   reflection passes, generating candidate analyses tied to evidence.
4. **Decision.** Policy engines classify decision criticality, enforce required
   approvals, and write entries into the ledger with full rationale.
5. **Execution.** Integrations sync the approved plan to delivery tools,
   ensuring idempotent updates and clear change history.
6. **Monitoring.** Feedback signals, KPIs, and incidents close the loop by
   updating models, risks, and playbooks.

## Data contracts

- Events include `event_id`, `correlation_id`, timestamps, actor, evidence
  references, and security labels.
- Payloads embed schema versioning so consumers can evolve safely.
- Decision records capture `decision_type`, alternatives considered, risk
  posture, and policy checks performed.

## Plugin isolation

Plugins live under `plugins/` and declare:

- Event types they subscribe to and emit.
- External dependencies or credentials they require.
- SLA expectations and failure modes (timeout, partial data, retry policy).

Plugins should never import stage-specific helpers directly; instead they call
functions from `common/` or use HTTP/gRPC contracts if split into separate
services.

## Data lifecycle

- Raw artefacts stay in the ingestion buffer with retention policies attached.
- Normalised corpora populate retrieval indexes with per-tenant isolation.
- Intermediate reasoning artefacts live in encrypted object storage keyed by
  decision ledger IDs.
- Monitoring summarises telemetry into long-term warehouses for trend analysis.

## Walkthrough example

1. A research brief arrives via email and is captured by the ingestion
   connector.
2. Retention tags mark the document as containing PII, triggering masking rules.
3. A strategy question comes in; retrieval fetches relevant prior initiatives.
4. Reasoning agents compare historic outcomes, surface assumptions, and score
   confidence.
5. The decision module writes an approval task, attaching evidence snapshots and
   risk annotations.
6. Execution syncs the agreed plan to the project tracker and posts updates to
   collaboration tools.
7. Monitoring tracks leading indicators and emits alerts if forecasts deviate
   beyond tolerance.
