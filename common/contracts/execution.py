"""Execution stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class WorkPackage:
    """Unit of work synced to external delivery tooling."""

    external_id: str
    title: str
    status: str
    owner: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class ExecutionPlanDispatched(BaseEvent):
    """Event representing execution artefacts pushed downstream."""

    sync_target: str
    work_packages: list[WorkPackage] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
