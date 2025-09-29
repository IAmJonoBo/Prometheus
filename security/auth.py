"""OIDC helpers for Keycloak integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TokenResponse:
    """Represents a simple OAuth2 token exchange result."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None


async def get_admin_token(
    base_url: str, *, username: str, password: str
) -> TokenResponse:
    """Exchange credentials for an admin token.

    Replace this stub with an HTTP call to Keycloak's admin token endpoint.
    """

    raise NotImplementedError("Implement the direct grant flow against Keycloak.")


async def get_service_token(
    base_url: str,
    *,
    client_id: str,
    client_secret: str,
    audience: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> TokenResponse:
    """Obtain a client credentials token for server-to-server calls."""

    raise NotImplementedError(
        "Call the Keycloak token endpoint with client credentials."
    )
