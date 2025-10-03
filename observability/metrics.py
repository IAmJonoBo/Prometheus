"""Prometheus metrics helpers."""

from __future__ import annotations

import os
import socket
from typing import Any

from prometheus_client import (
    GC_COLLECTOR,
    PLATFORM_COLLECTOR,
    PROCESS_COLLECTOR,
    CollectorRegistry,
    Info,
    multiprocess,
    start_http_server,
)

_STARTED_ENDPOINTS: set[tuple[str, int]] = set()


def configure_metrics(
    namespace: str = "prometheus",
    *,
    host: str | None = None,
    port: int | None = None,
    extra_labels: dict[str, str] | None = None,
) -> CollectorRegistry:
    """Create a Prometheus registry and optionally expose an HTTP endpoint.

    Parameters
    ----------
    namespace:
        Metric namespace used in exported series.
    host, port:
        When set (or when :envvar:`PROMETHEUS_METRICS_PORT` is defined) a
        scraper endpoint is started via ``prometheus_client.start_http_server``.
    extra_labels:
        Labels injected into the ``service_info`` metric so operators can tag
        deployments with environment/region metadata.
    """

    multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = CollectorRegistry()
        for collector in (GC_COLLECTOR, PROCESS_COLLECTOR, PLATFORM_COLLECTOR):
            registry.register(collector)

    info = Info(
        f"{namespace}_service_info",
        "Service build/runtime metadata.",
        registry=registry,
    )
    labels: dict[str, Any] = {
        "service": namespace,
        "hostname": socket.gethostname(),
    }
    if extra_labels:
        labels.update(extra_labels)
    info.info({str(key): str(value) for key, value in labels.items()})

    port = port or _env_int("PROMETHEUS_METRICS_PORT")
    if port is not None:
        resolved_host = host or os.getenv("PROMETHEUS_METRICS_HOST")
        if resolved_host is None:
            resolved_host = "127.0.0.1"
        host = resolved_host
        endpoint = (host, port)
        if endpoint not in _STARTED_ENDPOINTS:
            start_http_server(port, addr=host, registry=registry)
            _STARTED_ENDPOINTS.add(endpoint)

    return registry


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
