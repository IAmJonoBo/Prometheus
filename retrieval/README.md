# Retrieval

The retrieval stage assembles context for reasoning by combining lexical and
semantic search against curated corpora.

## Responsibilities

- Maintain hybrid indexes powered by RapidFuzz, optional OpenSearch, and
  optional Qdrant backends with keyword-overlap or cross-encoder reranking.
- Ingest normalised documents and expose retrieval APIs through
  `RetrievalService`.
- Return scored passages with citations, metadata, and deduplicated snippets.
- Emit `RetrievalContextBundle` events for reasoning orchestrators.

## Inputs & outputs

- **Inputs:** `IngestionNormalised` events plus query strings from callers.
- **Outputs:** `RetrievalContextBundle` events with ranked passages, source
  handles, and strategy metadata.
- **Shared contracts:** `common/contracts/retrieval.py` defines
  `RetrievalContextBundle` and `RetrievedPassage`. Align updates with
  `docs/capability-map.md`.

## Components

- `HybridRetrieverBackend` coordinates lexical (`RapidFuzzLexicalBackend` or
  `OpenSearchLexicalBackend`), vector (`QdrantVectorBackend`), and reranker
  components.
- `InMemoryRetriever` provides an adapter for tests and offline profiles.
- `build_hybrid_retriever` constructs backends from config dictionaries,
  allowing optional modules to be skipped when dependencies are absent.
- Optional cross-encoder reranking (when model dependencies are installed)
  refines the final ranking.

## Observability

- Logging surfaces strategy metadata; future instrumentation will add
  latency metrics and recall proxies once evaluation suites land.

## Regression harness

- Seed corpora and regression samples using TOML datasets stored alongside
  configs (for example, `configs/defaults/retrieval_regression.toml`).
- Run `python -m retrieval.regression_cli configs/defaults/retrieval_regression.toml`
  to exercise the harness locally or in CI and gate changes on recall and
  precision thresholds.

## Backlog

- Automate freshness checks to detect stale shards and publish metrics once
  the evaluation harness is stable.
- Document multilingual retrieval strategy in `docs/performance.md` and add
  access-control enforcement once the policy engine exposes the signals.
