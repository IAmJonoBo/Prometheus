"""Utilities for inspecting recorded dry-run artefacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DryRunRecord:
    """Represents a stored dry-run execution on disk."""

    run_id: str
    root: Path
    manifest: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    actor: str | None
    query: str | None
    warnings: list[str]
    tracebacks: list[dict[str, Any]]

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def tracebacks_path(self) -> Path:
        return self.root / "tracebacks.json"


def list_runs(root: Path) -> list[DryRunRecord]:
    """Return dry-run records sorted by completion time (most recent first)."""

    if not root.exists():
        return []

    records: list[DryRunRecord] = []
    for candidate in sorted(root.iterdir()):
        if not candidate.is_dir():
            continue
        manifest = _safe_load(candidate / "manifest.json", {})
        tracebacks = _load_tracebacks(candidate / "tracebacks.json")
        record = DryRunRecord(
            run_id=str(manifest.get("run_id") or candidate.name),
            root=candidate,
            manifest=manifest,
            started_at=_parse_timestamp(manifest.get("started_at")),
            completed_at=_parse_timestamp(manifest.get("completed_at")),
            actor=_safe_str(manifest.get("actor")),
            query=_safe_str(manifest.get("query")),
            warnings=list(manifest.get("warnings") or ()),
            tracebacks=tracebacks,
        )
        records.append(record)

    records.sort(
        key=lambda record: (
            record.completed_at
            or record.started_at
            or datetime.fromtimestamp(0, tz=UTC)
        ),
        reverse=True,
    )
    return records


def select_run(root: Path, run_id: str | None) -> DryRunRecord | None:
    """Return the record matching ``run_id`` or the most recent run."""

    runs = list_runs(root)
    if not runs:
        return None
    if run_id is None:
        return runs[0]
    for record in runs:
        if record.run_id == run_id or record.root.name == run_id:
            return record
    return None


def load_tracebacks(record: DryRunRecord) -> list[dict[str, Any]]:
    """Load tracebacks for the provided record."""

    if record.tracebacks:
        return record.tracebacks
    return _load_tracebacks(record.tracebacks_path)


def _load_tracebacks(path: Path) -> list[dict[str, Any]]:
    payload = _safe_load(path, [])
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    return []


def _safe_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _parse_timestamp(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        candidate = datetime.fromisoformat(value)
    except ValueError:
        return None
    return candidate if candidate.tzinfo else candidate.replace(tzinfo=UTC)


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def iter_stage_outputs(manifest: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Yield stage output names and paths stored in the manifest."""

    outputs = manifest.get("stage_outputs")
    if not isinstance(outputs, dict):
        return ()
    pairs = sorted((str(name), str(path)) for name, path in outputs.items())
    return tuple(pairs)
