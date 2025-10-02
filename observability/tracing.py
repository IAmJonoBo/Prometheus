"""OpenTelemetry tracing helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

_TRACE_CONFIGURED = False


def configure_tracing(
    service_name: str,
    *,
    resource_attributes: Mapping[str, str] | None = None,
    console_exporter: bool | None = None,
) -> trace.TracerProvider:
    """Configure an OTLP exporter and register the global tracer provider."""

    global _TRACE_CONFIGURED
    if _TRACE_CONFIGURED:
        return trace.get_tracer_provider()

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    if endpoint.startswith("http://"):
        os.environ.setdefault("OTEL_EXPORTER_OTLP_INSECURE", "true")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

    attributes = {
        "service.name": service_name,
        "deployment.environment": os.getenv("PROMETHEUS_ENV", "development"),
    }
    if resource_attributes:
        attributes.update(resource_attributes)

    provider = TracerProvider(resource=Resource.create(attributes))
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)

    enable_console = (
        console_exporter
        if console_exporter is not None
        else os.getenv("PROMETHEUS_TRACE_CONSOLE", "false").lower()
        in {"1", "true", "yes"}
    )
    if enable_console:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _TRACE_CONFIGURED = True
    return provider
