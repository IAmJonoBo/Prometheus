"""Execution adapters that integrate with external systems."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

from common.contracts import DecisionRecorded

from .service import ExecutionAdapter


@dataclass(slots=True)
class TemporalExecutionAdapter(ExecutionAdapter):
    """Dispatch decisions to a Temporal workflow."""

    target_host: str
    namespace: str
    task_queue: str
    workflow: str
    notes: list[str] = field(default_factory=list)

    def dispatch(self, decision: DecisionRecorded) -> Iterable[str]:
        client_module = _load_temporal_client()
        if client_module is None:  # pragma: no cover - optional dependency
            message = (
                "temporalio is not installed; skipped Temporal dispatch"
            )
            self.notes.append(message)
            return [message]

        async def _dispatch() -> str:
            module = cast(Any, client_module)
            client = await module.Client.connect(
                self.target_host,
                namespace=self.namespace,
            )
            handle = await client.start_workflow(
                self.workflow,
                decision.to_dict(),
                id=decision.meta.event_id,
                task_queue=self.task_queue,
            )
            return f"Temporal workflow started: {handle.id}"

        try:
            message = asyncio.run(_dispatch())
        except Exception as exc:  # pragma: no cover - network or runtime failure
            message = f"Temporal dispatch failed: {exc}"
        self.notes.append(message)
        return [message]


def _load_temporal_client() -> Any | None:
    """Return the Temporal client module when available."""

    try:
        return importlib.import_module("temporalio.client")
    except ImportError:
        return None


@dataclass(slots=True)
class WebhookExecutionAdapter(ExecutionAdapter):
    """Dispatch decisions to a webhook for downstream automation."""

    endpoint: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 10.0
    notes: list[str] = field(default_factory=list)

    def dispatch(self, decision: DecisionRecorded) -> Iterable[str]:
        import json

        import requests

        payload = json.dumps(decision.to_dict(), ensure_ascii=False)
        try:
            response = requests.post(
                self.endpoint,
                data=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json", **self.headers},
            )
            response.raise_for_status()
            message = f"Webhook accepted decision with status {response.status_code}"
        except requests.RequestException as exc:  # pragma: no cover - network failure path
            message = f"Webhook dispatch failed: {exc}"
        self.notes.append(message)
        return [message]

