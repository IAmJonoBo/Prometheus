"""Async scheduler coordinating ingestion connector execution."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from secrets import SystemRandom

from .connectors import SourceConnector
from .models import IngestionPayload

_JITTER_RANDOM = SystemRandom()


@dataclass(slots=True)
class SchedulerMetrics:
    """Telemetry captured from a scheduler run."""

    connectors_total: int = 0
    connectors_succeeded: int = 0
    connectors_failed: int = 0
    attempts: int = 0
    retries: int = 0


class RateLimiter:
    """Naïve rate limiter enforcing minimum spacing between tasks."""

    def __init__(self, rate_per_second: float) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self._interval = 1.0 / rate_per_second
        self._lock = asyncio.Lock()
        self._last_ts = 0.0

    async def acquire(self) -> None:
        """Wait until the next slot is available."""

        async with self._lock:
            now = time.perf_counter()
            wait_for = self._interval - (now - self._last_ts)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_ts = time.perf_counter()


class IngestionScheduler:
    """Coordinate asynchronous collection with retries and rate limiting."""

    def __init__(
        self,
        connectors: Sequence[SourceConnector],
        *,
        concurrency: int,
        max_retries: int,
        initial_backoff: float,
        max_backoff: float,
        jitter: float,
        rate_limit_per_second: float | None = None,
    ) -> None:
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        self._connectors = connectors
        self._semaphore = asyncio.Semaphore(concurrency)
        self._max_retries = max(0, max_retries)
        self._initial_backoff = max(0.0, initial_backoff)
        self._max_backoff = max(self._initial_backoff, max_backoff)
        self._jitter = max(0.0, jitter)
        self._rate_limiter = (
            RateLimiter(rate_limit_per_second) if rate_limit_per_second else None
        )
        self._metrics = SchedulerMetrics()
        self._metrics_lock = asyncio.Lock()

    async def run(self) -> list[IngestionPayload]:
        """Execute all connectors and aggregate their payloads."""

        tasks = [
            asyncio.create_task(self._run_connector(connector))
            for connector in self._connectors
        ]
        results = await asyncio.gather(*tasks)
        payloads: list[IngestionPayload] = []
        for result in results:
            payloads.extend(result)
        return payloads

    @property
    def metrics(self) -> SchedulerMetrics:
        """Return a snapshot of the last recorded metrics."""

        current = self._metrics
        return SchedulerMetrics(
            connectors_total=current.connectors_total,
            connectors_succeeded=current.connectors_succeeded,
            connectors_failed=current.connectors_failed,
            attempts=current.attempts,
            retries=current.retries,
        )

    async def _run_connector(
        self, connector: SourceConnector
    ) -> list[IngestionPayload]:
        async with self._semaphore:
            await self._record_metric("connectors_total", 1)
            attempt = 0
            while True:
                await self._record_metric("attempts", 1)
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()
                try:
                    result = await connector.collect_async()
                except Exception:  # pragma: no cover - surfaced in tests
                    attempt += 1
                    await self._record_metric("retries", 1)
                    if attempt > self._max_retries:
                        await self._record_metric("connectors_failed", 1)
                        raise
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                await self._record_metric("connectors_succeeded", 1)
                if isinstance(result, list):
                    return result
                return list(result)

    def _backoff(self, attempt: int) -> float:
        exponent = attempt - 1
        backoff = self._initial_backoff * (2**exponent)
        backoff = min(backoff, self._max_backoff)
        if self._jitter:
            backoff += _JITTER_RANDOM.uniform(0.0, self._jitter)
        return backoff

    async def _record_metric(self, field: str, increment: int) -> None:
        async with self._metrics_lock:
            setattr(self._metrics, field, getattr(self._metrics, field) + increment)
