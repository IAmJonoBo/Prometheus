"""Policy enforcement stubs for OpenFGA or Oso."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Decision(str, Enum):
    """Binary decision outcome for policy checks."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(slots=True)
class AuthorizationDecision:
    """Full result from the policy engine."""

    decision: Decision
    reason: str | None = None


class PolicyClient(Protocol):
    """Defines the operations required for policy backends."""

    async def check(
        self,
        user: str,
        relation: str,
        resource: str,
        context: dict[str, str] | None = None,
    ) -> AuthorizationDecision: ...


class OpenFGAClient:
    """Stub OpenFGA client awaiting a real HTTP implementation."""

    async def check(
        self,
        user: str,
        relation: str,
        resource: str,
        context: dict[str, str] | None = None,
    ) -> AuthorizationDecision:
        raise NotImplementedError("Invoke the OpenFGA /check endpoint.")
