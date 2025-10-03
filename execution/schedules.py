"""Temporal schedule helpers for dependency automation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from execution import workflows

try:  # pragma: no cover - optional dependency wiring
    from temporalio.client import (
        Client,
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleHandle,
        ScheduleOverlapPolicy,
        SchedulePolicy,
        ScheduleSpec,
    )
    from temporalio.service import RPCError, RPCStatusCode
except ImportError:  # pragma: no cover - fallback when temporalio missing
    Client = None  # type: ignore[assignment]
    Schedule = None  # type: ignore[assignment]
    ScheduleActionStartWorkflow = None  # type: ignore[assignment]
    ScheduleHandle = None  # type: ignore[assignment]
    SchedulePolicy = None  # type: ignore[assignment]
    ScheduleSpec = None  # type: ignore[assignment]
    ScheduleOverlapPolicy = None  # type: ignore[assignment]
    RPCError = Exception  # type: ignore[assignment]
    RPCStatusCode = None  # type: ignore[assignment]


DEFAULT_SCHEDULE_ID = "dependency-snapshot-weekly"
DEFAULT_CRON = ("0 6 * * 1",)
DEFAULT_TIMEZONE = "UTC"


@dataclass(slots=True)
class DependencySnapshotScheduleConfig:
    """Configuration for dependency snapshot Temporal schedule."""

    schedule_id: str = DEFAULT_SCHEDULE_ID
    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "prometheus-pipeline"
    cron_expressions: tuple[str, ...] = DEFAULT_CRON
    timezone: str = DEFAULT_TIMEZONE
    request: workflows.DependencySnapshotRequest | Mapping[str, Any] | None = None
    notification: (
        workflows.DependencySnapshotNotification | Mapping[str, Any] | None
    ) = None
    catchup_window: timedelta = timedelta(hours=2)
    notes: str | None = None


def serialize_dependency_snapshot_schedule(
    config: DependencySnapshotScheduleConfig,
) -> dict[str, Any]:
    """Return a serializable description of the schedule configuration."""

    request_payload = workflows._request_to_mapping(config.request)
    notification_payload = workflows._notification_to_mapping(config.notification)
    return {
        "schedule_id": config.schedule_id,
        "host": config.host,
        "namespace": config.namespace,
        "task_queue": config.task_queue,
        "cron": list(config.cron_expressions),
        "timezone": config.timezone,
        "catchup_window_seconds": int(config.catchup_window.total_seconds()),
        "request": request_payload,
        "notification": notification_payload,
        "notes": config.notes,
    }


async def ensure_dependency_snapshot_schedule(
    config: DependencySnapshotScheduleConfig,
) -> str:
    """Create or replace the dependency snapshot schedule."""

    if (
        Client is None
        or Schedule is None
        or ScheduleSpec is None
        or SchedulePolicy is None
        or ScheduleActionStartWorkflow is None
        or RPCStatusCode is None
    ):  # pragma: no cover - guard
        raise RuntimeError(
            "temporalio must be installed to manage dependency snapshot schedules."
        )

    payload = serialize_dependency_snapshot_schedule(config)

    client = await Client.connect(config.host, namespace=config.namespace)

    action = ScheduleActionStartWorkflow(
        workflows.DependencySnapshotWorkflow.run,
        args=[payload["request"], payload["notification"]],
        id=f"{config.schedule_id}-workflow",
        task_queue=config.task_queue,
    )

    overlap = (
        ScheduleOverlapPolicy.BUFFER_ONE if ScheduleOverlapPolicy is not None else None
    )
    policy_kwargs: dict[str, Any] = {
        "catchup_window": config.catchup_window,
    }
    if overlap is not None:
        policy_kwargs["overlap"] = overlap

    schedule_definition = Schedule(
        action=action,
        spec=ScheduleSpec(
            cron_expressions=payload["cron"],
            time_zone_name=config.timezone,
        ),
        policy=SchedulePolicy(**policy_kwargs),
    )

    handle = client.get_schedule_handle(config.schedule_id)
    exists = False
    try:
        await handle.describe()
    except RPCError as exc:
        if getattr(exc, "status", None) != RPCStatusCode.NOT_FOUND:
            raise
    else:
        exists = True

    if exists:
        try:
            await handle.delete()
        except RPCError as exc:
            if getattr(exc, "status", None) != RPCStatusCode.NOT_FOUND:
                raise
            exists = False

    await client.create_schedule(
        config.schedule_id,
        schedule_definition,
    )
    return "recreated" if exists else "created"
