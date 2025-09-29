# Prometheus SDK

The `sdk` package hosts developer-facing helpers for embedding Prometheus in
other applications. The initial surface currently exposes:

- `PrometheusClient`: thin wrapper around the pipeline orchestrator that lets
  you run queries programmatically without going through the CLI.

Future work will layer richer helpers for streaming events, subscribing to the
monitoring feed, and generating strategy artefacts directly from notebooks or
other automation.
