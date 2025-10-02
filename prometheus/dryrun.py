"""Dry-run orchestration utilities for the Prometheus pipeline."""

from __future__ import annotations

import json
import shutil
import traceback
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from common.contracts import BaseEvent

from .config import RuntimeConfig

_DEFAULT_MODE = "dryrun-%Y%m%dT%H%M%S"

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .pipeline import PipelineResult


@dataclass(slots=True)
class DryRunSession:
    """Represents an in-flight dry-run recording session."""

    run_id: str
    root: Path
    started_at: datetime
    query: str
    actor: str | None
    stage_paths: dict[str, Path] = field(default_factory=dict)
    manifest_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    tracebacks_path: Path | None = None
    _tracebacks: list[dict[str, Any]] = field(default_factory=list, repr=False)


@dataclass(slots=True)
class DryRunOutcome:
    """Summary of a completed dry-run execution."""

    run_id: str
    root: Path
    manifest_path: Path
    events_path: Path
    metrics_path: Path
    stage_paths: Mapping[str, Path]
    warnings: list[str]
    resource_usage: dict[str, Any] | None = None
    lineage_path: Path | None = None
    tracebacks_path: Path | None = None


@dataclass(slots=True)
class DryRunExecution:
    """Pair of pipeline output and dry-run artefact summary."""

    pipeline: PipelineResult
    outcome: DryRunOutcome


class DryRunRecorder:
    """Handles artefact persistence for dry-run executions."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config

    def start(self, query: str, actor: str | None) -> DryRunSession:
        run_root = Path(self._config.artifact_root).expanduser().resolve()
        run_root.mkdir(parents=True, exist_ok=True)
        self._cleanup_expired_runs(run_root)
        timestamp = datetime.now(UTC).strftime(_DEFAULT_MODE)
        for _ in range(5):
            run_id = f"{timestamp}-{uuid4().hex[:8]}"
            session_root = run_root / run_id
            try:
                session_root.mkdir(parents=False, exist_ok=False)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("Unable to allocate unique dry-run directory")
        session = DryRunSession(
            run_id=run_id,
            root=session_root,
            started_at=datetime.now(UTC),
            query=query,
            actor=actor,
        )
        manifest = {
            "run_id": run_id,
            "query": query,
            "actor": actor,
            "mode": self._config.mode,
            "started_at": session.started_at.isoformat(),
            "artifact_root": str(session_root),
            "feature_flags": dict(self._config.feature_flags),
        }
        manifest_path = session_root / "manifest.json"
        session.manifest_path = manifest_path
        _write_json(manifest_path, manifest)
        return session

    def record_stage(self, session: DryRunSession, stage: str, payload: Any) -> Path:
        path = session.root / f"{_safe_name(stage)}.json"
        data = _normalise(payload)
        _write_json(path, data)
        session.stage_paths[stage] = path
        return path

    def record_events(
        self, session: DryRunSession, events: Iterable[BaseEvent]
    ) -> Path:
        path = session.root / "events.json"
        data = [_normalise(event) for event in events]
        _write_json(path, data)
        return path

    def record_metrics(self, session: DryRunSession, metrics: Any) -> Path:
        path = session.root / "metrics.json"
        data = _normalise(metrics)
        _write_json(path, data)
        return path

    def record_traceback(
        self,
        session: DryRunSession,
        stage: str,
        error: BaseException,
    ) -> None:
        entry = {
            "stage": stage,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exception(
                type(error), error, error.__traceback__
            ),
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        session._tracebacks.append(entry)
        if session.tracebacks_path is None:
            session.tracebacks_path = session.root / "tracebacks.json"
        _write_json(session.tracebacks_path, session._tracebacks)

    def finalise(
        self,
        session: DryRunSession,
        *,
        events_path: Path,
        metrics_path: Path,
        warnings: Iterable[str] | None = None,
    ) -> DryRunOutcome:
        finished_at = datetime.now(UTC)
        usage = _collect_resource_usage()

        manifest = {
            "run_id": session.run_id,
            "query": session.query,
            "actor": session.actor,
            "mode": self._config.mode,
            "started_at": session.started_at.isoformat(),
            "completed_at": finished_at.isoformat(),
            "duration_seconds": max(
                0.0, (finished_at - session.started_at).total_seconds()
            ),
            "artifact_root": str(session.root),
            "stage_outputs": {
                name: str(path) for name, path in session.stage_paths.items()
            },
            "feature_flags": dict(self._config.feature_flags),
            "warnings": list(warnings or ()),
        }
        if usage is not None:
            manifest["resource_usage"] = usage
        if session.manifest_path is None:
            raise RuntimeError("DryRunSession missing manifest path")
        _write_json(session.manifest_path, manifest)
        return DryRunOutcome(
            run_id=session.run_id,
            root=session.root,
            manifest_path=session.manifest_path,
            events_path=events_path,
            metrics_path=metrics_path,
            stage_paths=dict(session.stage_paths),
            warnings=list(warnings or ()),
            resource_usage=usage,
            tracebacks_path=session.tracebacks_path,
        )

    def _cleanup_expired_runs(self, run_root: Path) -> None:
        retention_days = self._config.retention_days
        if retention_days <= 0:
            return
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        for candidate in run_root.iterdir():
            if not candidate.is_dir():
                continue
            completed_at = _candidate_completed_at(candidate)
            if completed_at is None:
                continue
            if completed_at < cutoff:
                _remove_path(candidate)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _safe_name(raw: str) -> str:
    return raw.replace("/", "_").replace(" ", "_")


def _normalise(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _normalise(value.to_dict())
        except TypeError:
            pass
    if is_dataclass(value) and not isinstance(value, type):
        return _normalise(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _normalise(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalise(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return repr(value)


__all__ = [
    "DryRunExecution",
    "DryRunOutcome",
    "DryRunRecorder",
    "DryRunSession",
]


def _parse_timestamp(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _remove_path(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError:  # pragma: no cover - best effort clean-up
        pass


def _candidate_completed_at(path: Path) -> datetime | None:
    manifest = path / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        timestamp = _parse_timestamp(data.get("completed_at"))
        if timestamp is None:
            timestamp = _parse_timestamp(data.get("started_at"))
        if timestamp is not None:
            return timestamp
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def _collect_resource_usage() -> dict[str, Any] | None:
    try:
        import resource
    except ImportError:  # pragma: no cover - unavailable on some platforms
        return None

    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "max_rss_kb": usage.ru_maxrss,
        "user_time_seconds": usage.ru_utime,
        "system_time_seconds": usage.ru_stime,
        "voluntary_ctx_switches": usage.ru_nvcsw,
        "involuntary_ctx_switches": usage.ru_nivcsw,
    }
