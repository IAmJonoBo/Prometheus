"""OpenTelemetry tracing helpers."""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Mapping

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)

LOGGER = logging.getLogger(__name__)

_TRACE_CONFIGURED = False


def _load_otlp_exporter() -> type[SpanExporter] | None:
    """Return the OTLP span exporter class if the dependency is installed."""

    try:
        module = importlib.import_module(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
        )
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        return None

    exporter = getattr(module, "OTLPSpanExporter", None)
    if exporter is None:
        LOGGER.warning("OTLPSpanExporter not found in exporter module.")
        return None
    if not isinstance(exporter, type):
        LOGGER.warning("OTLPSpanExporter is not a type; ignoring exporter.")
        return None
    if not issubclass(exporter, SpanExporter):
        LOGGER.warning("OTLPSpanExporter is not a SpanExporter subclass.")
        return None

    return exporter


def configure_tracing(
    service_name: str,
    *,
    resource_attributes: Mapping[str, str] | None = None,
    console_exporter: bool | None = None,
) -> trace.TracerProvider:
    """Configure tracing with OTLP exporter when available."""

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

    exporter_cls = _load_otlp_exporter()
    if exporter_cls is None:
        LOGGER.warning(
            "OTLP exporter is unavailable; falling back to console spans only. "
            "Install prometheus[observability] to enable OTLP exports."
        )
    else:
        processor = BatchSpanProcessor(exporter_cls())
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
