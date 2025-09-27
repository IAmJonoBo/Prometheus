1. Stand up OpenSearch + Qdrant clusters with cross-encoder rerankers (e.g.,
   sentence-transformers) and add regression/evaluation harnesses.
2. Deliver Temporal worker implementations plus Prometheus/Grafana dashboards
   wired to OTLP exporters for end-to-end observability.
3. Expose ingestion scheduler and PII masking metrics, validate configuration
   on load, and extend coverage with integration tests hitting live services.
