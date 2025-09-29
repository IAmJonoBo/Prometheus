"""Structured logging helpers aligned with the observability stack."""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import UTC, datetime
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter so we avoid an extra dependency."""

    def __init__(self, service_name: str | None = None) -> None:
        super().__init__()
        self._service = service_name or "prometheus-os"

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - stdlib signature
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "hostname": socket.gethostname(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in payload:
                continue
            if key in {
                "msg",
                "args",
                "levelname",
                "levelno",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "process",
                "processName",
                "exc_info",
                "stack_info",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str = "INFO",
    *,
    service_name: str | None = None,
) -> logging.Logger:
    """Configure structured logging for the application.

    The configuration prefers environment overrides (`PROMETHEUS_LOG_LEVEL`)
    and emits JSON documents compatible with Loki/Stackdriver style sinks.
    Subsequent calls replace the root handlers so the helper can be used in
    unit tests without duplicating log records.
    """

    resolved_level = os.getenv("PROMETHEUS_LOG_LEVEL", level).upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter(service_name=service_name))
    root_logger.addHandler(handler)

    logging.captureWarnings(True)
    return root_logger
