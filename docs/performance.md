# Performance

Prometheus balances responsiveness with accuracy and cost. This guide captures
service-level objectives, telemetry expectations, and capacity planning tips for
maintainers.

## Target SLOs

- **Ingestion latency:** < 2 minutes from source arrival to normalised event.
- **Retrieval latency:** p95 < 800 ms for hybrid search over 10M documents.
- **Reasoning turnaround:** p95 < 30 seconds for standard analyses with fallbacks.
- **Decision ledger writes:** p99 < 3 seconds including policy checks.
- **Execution sync:** 5 minutes max to propagate approved plans to delivery
  tools.

## Telemetry instrumentation

- Emit RED metrics (rate, errors, duration) per stage with consistent labels
  (`stage`, `event_type`, `tenant`).
- Attach correlation IDs to traces so a single decision can be reconstructed end
  to end.
- Log slow-path exemplars with input size, provider choice, and retry counts.
- Track cost per event (compute, model tokens, storage) to inform routing rules.

## Capacity planning

- Provision retrieval indexes with shards sized for 1.5x projected peak volume.
- Run monthly load tests simulating 3x normal throughput to validate headroom.
- Autoscale reasoning workers based on concurrent task backlog and GPU/CPU
  saturation.
- Cache hot evidence passages while respecting TTLs and access controls.

## Optimisation playbook

1. Identify the bottleneck using distributed tracing and cost dashboards.
2. Evaluate alternative model routes or prompt compression when latency spikes.
3. Tune chunking, reranker depth, and deduplication thresholds for retrieval.
4. Offload long-running analyses to asynchronous queues with user notifications.
5. Archive cold decision records to cheaper storage tiers once retention allows.
