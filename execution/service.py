"""Execution dispatch surface."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from common.contracts import DecisionRecorded, EventMeta, ExecutionPlanDispatched


@dataclass(slots=True, kw_only=True)
class ExecutionConfig:
    """Configuration for downstream synchronisation."""

    sync_target: str
    adapter: dict[str, Any] | None = None


class ExecutionAdapter:
    """Adapter interface for concrete execution targets."""

    def dispatch(self, decision: DecisionRecorded) -> Iterable[str]:
        """Dispatch the decision to the sync target."""

        raise NotImplementedError


class ExecutionService:
    """Converts decisions into actionable work packages."""

    def __init__(self, config: ExecutionConfig, adapter: ExecutionAdapter) -> None:
        self._config = config
        self._adapter = adapter

    def sync(
        self, decision: DecisionRecorded, meta: EventMeta
    ) -> ExecutionPlanDispatched:
        """Synchronise decision outcomes into external tooling."""

        notes = list(self._adapter.dispatch(decision))
        return ExecutionPlanDispatched(
            meta=meta,
            sync_target=self._config.sync_target,
            notes=notes,
        )
