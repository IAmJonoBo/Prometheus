# Retrieval

The retrieval stage assembles context for reasoning by combining lexical and
semantic search against curated corpora.

## Responsibilities

- Maintain hybrid indexes (BM25, dense embeddings, rerankers) with freshness
  guarantees.
- Enforce per-tenant access controls and masking policies during lookup.
- Return scored passages with citations, metadata, and deduplicated snippets.
- Emit `Retrieval.ContextBundle` events for reasoning orchestrators.

## Inputs & outputs

- **Inputs:** `Ingestion.Normalised` events, user queries, filter directives,
  and profile signals.
- **Outputs:** `Retrieval.ContextBundle` events with ranked passages, source
  handles, and feature flags describing retrieval strategy.
- **Shared contracts:** Define schemas in `common/contracts/retrieval.py`
  (placeholder) and align doc updates with `docs/capability-map.md`.

## Components

- Corpus manager for indexing pipelines, shard rotation, and schema evolution.
- Query planner that blends lexical, embedding, and structured lookups.
- Reranker library (OSS-first) with guardrails for hallucinated citations.
- Cache layer for hot passages with TTL and invalidation hooks.

## Observability

- Track metrics: recall/precision proxies, latency percentiles, cache hit rate.
- Annotate traces with strategy details (index versions, reranker choice).
- Produce evaluation datasets for continuous benchmarking in
  `docs/model-strategy.md` workflows.

## Regression harness

- Seed corpora and regression samples using TOML datasets stored alongside
  configs (for example, `configs/defaults/retrieval_regression.toml`).
- Run `python -m retrieval.regression_cli configs/defaults/retrieval_regression.toml`
  to exercise the harness locally or in CI and gate changes on recall/precision
  thresholds.

## Backlog

- Finalise `Retrieval.ContextBundle` schema in `common/` and tests in `tests/`.
- Automate freshness checks to detect stale shards.
- Document multilingual retrieval strategy in `docs/performance.md`.
