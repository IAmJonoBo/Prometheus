# Ingestion

The ingestion stage captures raw intelligence from heterogeneous sources and
converts it into `IngestionNormalised` events ready for retrieval.

## Responsibilities

- Collect content from filesystem, web, and synthetic connectors (stubs live
  under `ingestion/connectors.py`).
- Normalise text payloads, inject provenance metadata, and persist artefacts
  via the configured document store (SQLite or in-memory).
- Scrub or mask PII while preserving provenance tags for downstream auditing
  using the built-in `PIIRedactor` helper.
- Emit `IngestionNormalised` events with attachment manifests and retention
  hints.

## Inputs & outputs

- **Inputs:** Source-specific payloads gathered by connectors and the
  asynchronous scheduler.
- **Outputs:** `IngestionNormalised` events published to the event bus with
  attachment manifests and provenance metadata.
- **Shared contracts:** `common/contracts/ingestion.py` defines
  `IngestionNormalised` and attachment schemas. Update
  `docs/capability-map.md` when schema fields evolve.

## Components

- `SourceConnector` implementations:
  - `MemoryConnector` for synthetic payloads and tests.
  - `FileSystemConnector` with optional Unstructured partitioning and
    checksum tracking.
  - `WebConnector` that uses `requests`/`httpx` plus `trafilatura` when
    installed to extract HTML.
- `IngestionScheduler` coordinates connectors concurrently with retry,
  backoff, and optional rate limiting (see `SchedulerConfig`).
- `SQLiteDocumentStore` provides durable persistence; swap to the
  in-memory store for tests.
- `PIIRedactor` masks entities inline, recording detected labels for
  downstream auditing.

## Observability

- `IngestionRunMetrics` aggregates scheduler counters plus redaction stats and
  feeds them into the monitoring stage as `MetricSample` entries.
- Logging falls back to Python's standard logging hooks; extend the scheduler
  if trace IDs are required.

## Backlog

- Extend connectors for email, APIs, and streaming feeds with capability
  metadata once requirements land.
- Chunk large documents for downstream vectorisation and revise the schema to
  include content fingerprints.
- Document retention policies per source family in `docs/quality-gates.md` and
  expand metrics to cover ingestion latency distributions.
