# Ingestion

The ingestion stage captures raw intelligence from heterogeneous sources and
converts it into normalised events ready for retrieval.

## Responsibilities

- Connect to pull and push feeds (email, file drops, APIs, web crawlers).
- Normalise formats (text, spreadsheets, slides) and extract structured
  metadata.
- Scrub or mask PII while preserving provenance tags for downstream auditing.
- Emit `Ingestion.Normalised` events with attachment manifests and retention
  policies.

## Inputs & outputs

- **Inputs:** Source-specific payloads delivered via connectors or schedulers.
- **Outputs:** `Ingestion.Normalised` events written to the event bus and
  staging storage, with references recorded in the decision ledger.
- **Shared contracts:** Define schemas in `common/contracts/ingestion.py`
  (placeholder) and keep docs in `docs/capability-map.md` up to date.

## Components

- Connector registry with capability flags (auth method, throttle limits,
  supported MIME types).
- Normalisation workers that chunk large documents for downstream vectorisation.
- Provenance tracker that records source IDs, timestamps, and masking decisions.
- PII detection service (OSS-first, fallback to provider APIs when required).

## Observability

- Emit metrics: ingestion latency, document size distribution, PII detection
  rate, masking coverage.
- Attach traces that span connector pull, normalisation, and event publish.
- Log sampling should capture representative payload metadata, not contents.

## Backlog

- Define the canonical `Ingestion.Normalised` schema under `common/`.
- Implement connector scaffolds with fixture-based integration tests.
- Document retention policies per source family in `docs/quality-gates.md`.
