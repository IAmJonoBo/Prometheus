"""Vault client scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class VaultClient:
    """Thin wrapper around HashiCorp Vault for secret retrieval."""

    address: str = "http://localhost:8200"
    token: str = "root"

    async def read_secret(self, path: str) -> dict[str, Any]:
        """Read a secret from Vault at the provided path."""

        raise NotImplementedError("Wire an HTTP client to Vault's KV API.")

    async def write_secret(self, path: str, data: dict[str, Any]) -> None:
        """Write or update a secret at the provided path."""

        raise NotImplementedError("Issue a write request to Vault's KV API.")
