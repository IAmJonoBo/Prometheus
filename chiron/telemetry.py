"""Enhanced telemetry for Chiron operations.

This module provides comprehensive observability for all Chiron subsystem operations,
including metrics, tracing, and structured logging.

Features:
- Operation timing and metrics
- Success/failure tracking
- Resource usage monitoring
- Structured event logging
- Integration with OpenTelemetry (when available)
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generator

logger = logging.getLogger(__name__)

# Try to import OpenTelemetry, but don't fail if not available
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


@dataclass
class OperationMetrics:
    """Metrics for a Chiron operation."""

    operation: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    success: bool | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_complete(self, success: bool, error: str | None = None) -> None:
        """Mark operation as complete.

        Args:
            success: Whether operation succeeded
            error: Error message if failed
        """
        self.completed_at = datetime.now(UTC)
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.success = success
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary representation of metrics
        """
        return {
            "operation": self.operation,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }


class ChironTelemetry:
    """Telemetry collector for Chiron operations."""

    def __init__(self) -> None:
        self._metrics: list[OperationMetrics] = []
        self._current_operations: dict[str, OperationMetrics] = {}

    def start_operation(self, operation: str, **metadata: Any) -> OperationMetrics:
        """Start tracking an operation.

        Args:
            operation: Operation name
            **metadata: Additional metadata

        Returns:
            Operation metrics object
        """
        metrics = OperationMetrics(
            operation=operation,
            started_at=datetime.now(UTC),
            metadata=metadata,
        )
        self._current_operations[operation] = metrics
        logger.debug(f"Started operation: {operation}", extra=metadata)
        return metrics

    def complete_operation(
        self,
        operation: str,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Mark an operation as complete.

        Args:
            operation: Operation name
            success: Whether operation succeeded
            error: Error message if failed
        """
        if operation not in self._current_operations:
            logger.warning(f"Operation '{operation}' not found in tracking")
            return

        metrics = self._current_operations.pop(operation)
        metrics.mark_complete(success, error)
        self._metrics.append(metrics)

        log_method = logger.info if success else logger.error
        log_method(
            f"Completed operation: {operation} "
            f"(duration: {metrics.duration_ms:.2f}ms, success: {success})"
        )

    def get_metrics(self) -> list[OperationMetrics]:
        """Get all recorded metrics.

        Returns:
            List of operation metrics
        """
        return self._metrics.copy()

    def clear_metrics(self) -> None:
        """Clear all recorded metrics."""
        self._metrics.clear()

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all operations.

        Returns:
            Summary statistics
        """
        total = len(self._metrics)
        if total == 0:
            return {"total": 0, "success": 0, "failure": 0, "avg_duration_ms": 0}

        success_count = sum(1 for m in self._metrics if m.success)
        failure_count = total - success_count

        durations = [m.duration_ms for m in self._metrics if m.duration_ms is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total": total,
            "success": success_count,
            "failure": failure_count,
            "avg_duration_ms": avg_duration,
        }


# Global telemetry instance
_telemetry = ChironTelemetry()


def get_telemetry() -> ChironTelemetry:
    """Get the global telemetry instance.

    Returns:
        ChironTelemetry instance
    """
    return _telemetry


@contextmanager
def track_operation(
    operation: str,
    **metadata: Any,
) -> Generator[OperationMetrics, None, None]:
    """Context manager for tracking an operation.

    Args:
        operation: Operation name
        **metadata: Additional metadata

    Yields:
        Operation metrics object

    Example:
        with track_operation("dependency_scan", package="numpy"):
            # Do work
            pass
    """
    metrics = _telemetry.start_operation(operation, **metadata)

    # Create OpenTelemetry span if available
    span = None
    if HAS_OTEL:
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span(operation)
        for key, value in metadata.items():
            span.set_attribute(key, str(value))

    try:
        yield metrics
        _telemetry.complete_operation(operation, success=True)
        if span:
            span.set_status(Status(StatusCode.OK))
    except Exception as exc:
        error_msg = str(exc)
        _telemetry.complete_operation(operation, success=False, error=error_msg)
        if span:
            span.set_status(Status(StatusCode.ERROR, error_msg))
            span.record_exception(exc)
        raise
    finally:
        if span:
            span.end()


__all__ = [
    "OperationMetrics",
    "ChironTelemetry",
    "get_telemetry",
    "track_operation",
]
