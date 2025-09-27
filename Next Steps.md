1. Layer in PII detection/redaction and asynchronous scheduling across the new
   ingestion connectors, including rate limiting and retry policies.
2. Stand up OpenSearch + Qdrant clusters with cross-encoder rerankers (e.g.,
   sentence-transformers) and add regression/evaluation harnesses.
3. Deliver Temporal worker implementations plus Prometheus/Grafana dashboards
   wired to OTLP exporters for end-to-end observability.
