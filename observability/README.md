# Observability scaffold

Helpers for wiring the Python services to the local OpenTelemetry collector,
Prometheus, Loki, and Tempo. The modules now configure structured JSON
logging, an OTLP trace exporter, and a Prometheus registry/HTTP endpoint out of
the box so the pipeline matches the tech‑stack commitments.

Usage example:

```python
from observability import configure_logging, configure_metrics, configure_tracing

configure_logging(service_name="prometheus-pipeline")
configure_tracing("prometheus-pipeline")
configure_metrics(namespace="prometheus-pipeline")
```

Environment variables:

- `PROMETHEUS_LOG_LEVEL` (default `INFO`)
- `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://localhost:4317`)
- `PROMETHEUS_METRICS_PORT` and `PROMETHEUS_METRICS_HOST`
- `PROMETHEUS_MULTIPROC_DIR` for gunicorn/worker setups
- `PROMETHEUS_TRACE_CONSOLE` enables the console span exporter for debugging.
