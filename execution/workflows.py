"""Reference Temporal workflows and activities for Prometheus execution."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency wiring
    from temporalio import activity, workflow
except ImportError:  # pragma: no cover - fallback when temporalio missing

    def _identity_decorator(target=None, **_: Any):
        if target is not None:
            return target

        def decorator(func):
            return func

        return decorator

    class _WorkflowStub:
        def defn(self, target=None, **kwargs: Any):
            return _identity_decorator(target, **kwargs)

        def run(self, target=None, **kwargs: Any):
            return _identity_decorator(target, **kwargs)

    class _ActivityStub:
        def defn(self, target=None, **kwargs: Any):
            return _identity_decorator(target, **kwargs)

    workflow = _WorkflowStub()  # type: ignore
    activity = _ActivityStub()  # type: ignore


logger = logging.getLogger(__name__)


def _coerce_bool_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "off", "no"}:
            return False
        if normalized in {"1", "true", "on", "yes"}:
            return True
    return bool(value)


def _normalize_planner_packages(data: dict[str, Any]) -> None:
    packages = data.get("planner_packages")
    if packages is None:
        data["planner_packages"] = None
        return
    if isinstance(packages, str):
        candidates = packages.split(",")
    else:
        try:
            candidates = list(packages)  # type: ignore[arg-type]
        except TypeError:
            candidates = [packages]
    tokens = [str(token).strip() for token in candidates if str(token).strip()]
    data["planner_packages"] = tuple(tokens) or None


def _normalize_bool_fields(data: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in data:
            data[field] = _coerce_bool_flag(data[field])


@dataclass(slots=True)
class WorkerContext:
    """Context emitted by the default workflow/activity pair."""

    decision_id: str
    notes: list[str]
    status: str


@dataclass(slots=True)
class DependencySnapshotRequest:
    """Input configuration for automated dependency snapshot refresh."""

    contract_path: str | None = None
    sbom_path: str | None = None
    metadata_path: str | None = None
    preflight_path: str | None = None
    fail_threshold: str = "needs-review"
    planner_enabled: bool = True
    planner_packages: tuple[str, ...] | None = None
    planner_allow_major: bool = False
    planner_limit: int | None = None
    planner_run_resolver: bool = False
    planner_poetry: str | None = None
    planner_project_root: str | None = None
    report_path: str | None = None


@dataclass(slots=True)
class DependencySnapshotNotification:
    """Notification options for dependency snapshot automation."""

    channel: str = "log"
    path: str | None = None
    severity_threshold: str = "needs-review"


@dataclass(slots=True)
class DependencySnapshotResult:
    """Structured result returned by the dependency snapshot workflow."""

    summary: dict[str, Any]
    exit_code: int
    generated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.summary)
        payload["exit_code"] = self.exit_code
        payload["generated_at"] = self.generated_at.isoformat()
        return payload


@workflow.defn
class PrometheusPipelineWorkflow:
    """Temporal workflow that mirrors decision payloads for auditing."""

    @workflow.run
    async def run(self, decision_payload: dict[str, Any]) -> WorkerContext:
        event_id = decision_payload.get("meta", {}).get("event_id", "unknown")
        notes = decision_payload.get("notes", [])
        return WorkerContext(decision_id=event_id, notes=list(notes), status="received")


@activity.defn
async def record_decision_activity(context: WorkerContext) -> dict[str, Any]:
    """Return a structured log payload for downstream sinks."""

    return {
        "decision_id": context.decision_id,
        "status": context.status,
        "note_count": len(context.notes),
    }


@activity.defn
async def emit_metrics_activity(context: WorkerContext) -> dict[str, Any]:
    """Provide metric-friendly representation for monitoring exporters."""

    return {
        "metric": "temporal.worker.decisions.processed",
        "value": 1.0,
        "attributes": {
            "decision_id": context.decision_id,
            "status": context.status,
        },
    }


def _coerce_snapshot_request(
    payload: DependencySnapshotRequest | Mapping[str, Any] | None,
) -> DependencySnapshotRequest:
    if isinstance(payload, DependencySnapshotRequest):
        return payload
    if payload is None:
        return DependencySnapshotRequest()
    if not isinstance(payload, Mapping):
        raise TypeError("Unsupported snapshot request payload")

    data = dict(payload)

    _normalize_planner_packages(data)
    _normalize_bool_fields(
        data,
        (
            "planner_enabled",
            "planner_allow_major",
            "planner_run_resolver",
        ),
    )

    return DependencySnapshotRequest(**data)


def _coerce_snapshot_notification(
    payload: DependencySnapshotNotification | Mapping[str, Any] | None,
) -> DependencySnapshotNotification:
    if isinstance(payload, DependencySnapshotNotification):
        return payload
    if payload is None:
        return DependencySnapshotNotification()
    if not isinstance(payload, Mapping):
        raise TypeError("Unsupported snapshot notification payload")
    data = dict(payload)
    if "channel" in data and data["channel"]:
        data["channel"] = str(data["channel"])
    if "path" in data and data["path"]:
        data["path"] = str(data["path"])
    if "severity_threshold" in data and data["severity_threshold"]:
        data["severity_threshold"] = str(data["severity_threshold"])
    return DependencySnapshotNotification(**data)


def _request_to_mapping(
    request: DependencySnapshotRequest | Mapping[str, Any] | None,
) -> dict[str, Any]:
    coerced = _coerce_snapshot_request(request)
    payload: dict[str, Any] = {
        "contract_path": coerced.contract_path,
        "sbom_path": coerced.sbom_path,
        "metadata_path": coerced.metadata_path,
        "preflight_path": coerced.preflight_path,
        "fail_threshold": coerced.fail_threshold,
        "planner_enabled": coerced.planner_enabled,
        "planner_allow_major": coerced.planner_allow_major,
        "planner_limit": coerced.planner_limit,
        "planner_run_resolver": coerced.planner_run_resolver,
        "planner_poetry": coerced.planner_poetry,
        "planner_project_root": coerced.planner_project_root,
        "report_path": coerced.report_path,
    }
    payload["planner_packages"] = (
        list(coerced.planner_packages) if coerced.planner_packages is not None else None
    )
    return payload


def _notification_to_mapping(
    notification: DependencySnapshotNotification | Mapping[str, Any] | None,
) -> dict[str, Any]:
    coerced = _coerce_snapshot_notification(notification)
    return {
        "channel": coerced.channel,
        "path": coerced.path,
        "severity_threshold": coerced.severity_threshold,
    }


def _resolve_optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()


def _severity_rank(value: str) -> int:
    order = {
        "unknown": 0,
        "ok": 0,
        "info": 0,
        "low": 1,
        "needs-review": 1,
        "moderate": 1,
        "medium": 1,
        "warning": 1,
        "high": 2,
        "critical": 2,
        "blocked": 2,
        "error": 2,
    }
    return order.get(value.lower(), 1)


def _generate_dependency_status(
    request: DependencySnapshotRequest,
) -> dict[str, Any]:
    from scripts import deps_status

    contract_path = _resolve_optional_path(request.contract_path)
    if contract_path is None:
        from scripts import upgrade_guard

        contract_path = upgrade_guard.DEFAULT_CONTRACT_PATH

    planner_packages = request.planner_packages
    if planner_packages is not None:
        package_filter = tuple(str(item) for item in planner_packages if item)
    else:
        package_filter = None

    planner_settings = deps_status.PlannerSettings(
        enabled=request.planner_enabled,
        packages=package_filter,
        allow_major=request.planner_allow_major,
        limit=request.planner_limit,
        skip_resolver=not request.planner_run_resolver,
        poetry=request.planner_poetry,
        project_root=_resolve_optional_path(request.planner_project_root),
    )

    status = deps_status.generate_status(
        preflight=_resolve_optional_path(request.preflight_path),
        renovate=None,
        cve=None,
        contract=contract_path,
        sbom=_resolve_optional_path(request.sbom_path),
        metadata=_resolve_optional_path(request.metadata_path),
        sbom_max_age_days=None,
        fail_threshold=request.fail_threshold,
        planner_settings=planner_settings,
    )

    payload = {
        "generated_at": status.generated_at.isoformat(),
        "exit_code": status.exit_code,
        "summary": dict(status.summary),
        "guard": status.guard.to_dict(),
        "planner": status.planner.to_dict() if status.planner else None,
    }

    if request.report_path:
        report_path = Path(request.report_path).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        payload["report_path"] = str(report_path)

    return payload


@activity.defn
async def run_dependency_snapshot_activity(
    config: DependencySnapshotRequest | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    request = _coerce_snapshot_request(config)
    result = _generate_dependency_status(request)
    severity = str(result.get("summary", {}).get("highest_severity", "unknown"))
    logger.info(
        "Dependency snapshot generated (severity=%s, exit_code=%s)",
        severity,
        result.get("exit_code"),
    )
    return result


@activity.defn
async def notify_dependency_snapshot_activity(
    snapshot: Mapping[str, Any],
    notification: DependencySnapshotNotification | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    notice = _coerce_snapshot_notification(notification)
    summary = snapshot.get("summary", {}) if isinstance(snapshot, Mapping) else {}
    severity = str(summary.get("highest_severity", "unknown"))
    should_deliver = _severity_rank(severity) >= _severity_rank(
        notice.severity_threshold
    )
    delivery: dict[str, Any] = {
        "channel": notice.channel,
        "severity": severity,
        "delivered": False,
    }
    if not should_deliver:
        logger.info(
            "Skipping dependency snapshot notification: severity %s below threshold %s",
            severity,
            notice.severity_threshold,
        )
        return delivery

    message = json.dumps(snapshot, indent=2, sort_keys=True)
    if notice.path:
        path = Path(notice.path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(message + "\n", encoding="utf-8")
        delivery["delivered"] = True
        delivery["path"] = str(path)
        logger.info("Wrote dependency snapshot notification to %s", path)
    else:
        logger.info(
            "Dependency snapshot notification (%s): %s", notice.channel, message
        )
        delivery["delivered"] = True

    return delivery


@workflow.defn
class DependencySnapshotWorkflow:
    """Temporal workflow that schedules dependency snapshot refresh runs."""

    @workflow.run
    async def run(
        self,
        request: DependencySnapshotRequest | Mapping[str, Any] | None = None,
        notification: DependencySnapshotNotification | Mapping[str, Any] | None = None,
    ) -> DependencySnapshotResult:
        request_payload = _request_to_mapping(request)
        notification_payload = _notification_to_mapping(notification)

        if hasattr(workflow, "execute_activity"):
            snapshot = await workflow.execute_activity(  # type: ignore[attr-defined]
                run_dependency_snapshot_activity,
                request_payload,
                start_to_close_timeout=timedelta(minutes=15),
            )
            await workflow.execute_activity(  # type: ignore[attr-defined]
                notify_dependency_snapshot_activity,
                snapshot,
                notification_payload,
                start_to_close_timeout=timedelta(minutes=5),
            )
        else:  # pragma: no cover - fallback when temporalio is unavailable
            snapshot = await run_dependency_snapshot_activity(request_payload)
            await notify_dependency_snapshot_activity(snapshot, notification_payload)

        summary = snapshot.get("summary", {}) if isinstance(snapshot, Mapping) else {}
        generated_at = summary.get("generated_at")
        if isinstance(generated_at, str):
            try:
                generated_dt = datetime.fromisoformat(generated_at)
            except ValueError:  # pragma: no cover - defensive guard
                generated_dt = datetime.now(UTC)
        else:
            generated_dt = datetime.now(UTC)

        exit_code = snapshot.get("exit_code", 0)
        try:
            exit_code_int = int(exit_code)
        except (TypeError, ValueError):  # pragma: no cover - defensive guard
            exit_code_int = 0

        return DependencySnapshotResult(
            summary=summary if isinstance(summary, dict) else {},
            exit_code=exit_code_int,
            generated_at=generated_dt,
        )
