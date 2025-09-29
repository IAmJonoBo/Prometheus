"""Prometheus metrics helpers."""

from __future__ import annotations

from prometheus_client import CollectorRegistry  # type: ignore


def configure_metrics(namespace: str = "prometheus") -> CollectorRegistry:
    """Return a registry ready for application metrics."""

    raise NotImplementedError("Register default metrics and exporters here.")
