# Performance

Prometheus targets frontier-grade responsiveness while maintaining accuracy and
cost discipline. Use these service-level objectives, telemetry expectations,
and optimisation levers to keep deployments within budget and within user
experience goals.

## Target SLOs

- **Ingestion latency:** p95 < 10 s for a 100-page document on a laptop; faster
  on server-class hardware.
- **Retrieval latency:** p50 ~50 ms, p95 < 200 ms against a 100k document
  corpus, including reranking.
- **Reasoning turnaround:** p50 < 2 s, p95 < 5 s for interactive Q&A with local
  models; long-form plans stream partial output within 10 s and complete within
  30 s.
- **Decision ledger writes:** p99 < 2 s including policy checks and approval
  hooks.
- **Execution sync:** < 60 s to reflect accepted plans in downstream tooling;
  bulk updates complete within 5 min with idempotent diffs.
- **Monitoring feedback:** leading indicator alerts propagate within 2 min from
  threshold breach; risk escalations within 5 min.

SLO breaches consume error budget. When any stage exceeds its budget over a
rolling window, pause risky deployments and prioritise optimisation.

## Auto-benchmarking & tuning

On first run the system benchmarks CPU, GPU, memory, and disk throughput to
select defaults:

- Choose quantised or distilled models for laptops; full-precision checkpoints
  for servers with ample GPU.
- Set ingestion parallelism and chunk sizes based on core count and memory.
- Warn when user-initiated tasks exceed available headroom and suggest enabling
  remote providers or asynchronous execution.

Benchmarks are cached but can be re-run with `scripts/benchmark-env.sh` after
hardware changes.

## Telemetry instrumentation

- Emit RED metrics per stage with labels `stage`, `event_type`, `tenant`, and
  `model_route`.
- Attach correlation and decision IDs to every span so traces cover ingestion
  through monitoring.
- Record cost metrics (compute, storage, token spend) to feed the model gateway
  routing policy.
- Capture exemplar traces of the slowest 1% of requests with payload size,
  provider choice, retries, and fallback decision.

## Scaling patterns

- **Single-machine:** Run all services in one process; rely on cooperative
  multitasking and caching. Use asynchronous queues for heavy reasoning tasks.
- **Horizontal scale:** Deploy ingestion, retrieval, reasoning, and monitoring
  as independent services behind queues. Autoscale reasoning workers based on
  backlog and GPU utilisation; shard retrieval indexes and warm caches for each
  shard.
- **High availability:** Use rolling updates or blue-green deployments with
  health checks. Keep dual indexes during migrations to avoid downtime.
- **Backpressure:** Apply circuit breakers when provider latency spikes; degrade
  gracefully by switching to smaller models or summarised retrieval when under
  stress.

## Optimisation playbook

1. Inspect distributed traces to locate the slow stage; validate whether compute
   or external dependency dominates.
2. Adjust retrieval knobs: chunk size, reranker depth, deduplication thresholds,
   and caching TTLs.
3. Update model gateway routing rules—prefer local distilled models for low-risk
   queries, cascade to larger models for critical tasks, and batch similar
   requests where possible.
4. Compress prompts and context windows using summarisation or citation pruning
   without violating groundedness gates.
5. Offload long-running analyses to asynchronous tasks with user notifications;
   expose progress indicators in the UI.
6. Archive cold decision artefacts to lower-cost storage once retention windows
   expire.

## Validation cadence

- Run monthly load tests at 3× expected throughput with representative corpora.
- Re-run auto-benchmarks and SLO checks after dependency upgrades or model
  swaps.
- Track SLO compliance and error budget burn in the monitoring dashboards and
  surface regressions in release readiness reviews.
