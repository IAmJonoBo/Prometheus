"""Logging configuration stubs."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging for the application."""

    raise NotImplementedError("Connect structlog or the standard logging tree.")
