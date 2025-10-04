"""Shared manifest helpers for offline packaging artefacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WheelhouseManifest:
    """Structured view of the wheelhouse manifest written by the orchestrator."""

    generated_at: str | None
    extras: tuple[str, ...]
    include_dev: bool
    create_archive: bool
    commit: str | None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> WheelhouseManifest:
        extras = tuple(str(item) for item in data.get("extras", []) if item)
        return cls(
            generated_at=(
                str(data.get("generated_at")) if data.get("generated_at") else None
            ),
            extras=extras,
            include_dev=bool(data.get("include_dev", False)),
            create_archive=bool(data.get("create_archive", False)),
            commit=str(data["commit"]) if data.get("commit") else None,
        )

    def to_json(self) -> str:
        payload = {
            "generated_at": self.generated_at,
            "extras": list(self.extras),
            "include_dev": self.include_dev,
            "create_archive": self.create_archive,
            "commit": self.commit,
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def load_wheelhouse_manifest(path: Path) -> WheelhouseManifest:
    """Load a wheelhouse manifest from *path*.

    Parameters
    ----------
    path:
        Path to a JSON manifest file. An informative ``FileNotFoundError`` or
        ``RuntimeError`` is raised when the file cannot be read or parsed.
    """

    if not path.is_file():
        raise FileNotFoundError(f"Wheelhouse manifest not found at {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            f"Wheelhouse manifest at {path} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, Mapping):  # pragma: no cover - defensive
        raise RuntimeError(f"Wheelhouse manifest at {path} must be a JSON object")

    return WheelhouseManifest.from_mapping(data)


def write_wheelhouse_manifest(path: Path, manifest: WheelhouseManifest) -> None:
    """Serialize *manifest* to *path* and ensure the parent directory exists."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json(), encoding="utf-8")
