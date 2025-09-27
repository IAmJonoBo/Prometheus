"""Decision stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class ApprovalTask:
    """Represents a follow-up approval or escalation request."""

    assignee: str
    due_at: str
    status: str = "pending"
    notes: List[str] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class DecisionRecorded(BaseEvent):
    """Canonical decision record emitted downstream."""

    decision_type: str
    status: str
    rationale: str
    alternatives: List[str] = field(default_factory=list)
    approvals: List[ApprovalTask] = field(default_factory=list)
    policy_checks: Dict[str, str] = field(default_factory=dict)
