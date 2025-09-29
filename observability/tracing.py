"""OpenTelemetry tracing helpers."""

from __future__ import annotations

from opentelemetry import trace  # type: ignore


def configure_tracing(service_name: str) -> trace.TracerProvider:
    """Configure tracing exporters and return the provider."""

    raise NotImplementedError("Initialise the OTLP exporter towards the collector.")
