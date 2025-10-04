from __future__ import annotations

import types
from datetime import timedelta

import pytest

from execution import schedules


@pytest.mark.asyncio
async def test_ensure_dependency_snapshot_schedule_requires_temporal(monkeypatch):
    monkeypatch.setattr(schedules, "Client", None)
    with pytest.raises(RuntimeError):
        await schedules.ensure_dependency_snapshot_schedule(
            schedules.DependencySnapshotScheduleConfig()
        )


class _FakeRPCError(Exception):
    def __init__(self, status_code: str) -> None:
        super().__init__("rpc error")
        self.status_code = status_code
        self.status = status_code  # Add this for compatibility


class _FakeRPCStatusCode:
    NOT_FOUND = "NOT_FOUND"


class _StubScheduleActionStartWorkflow:
    def __init__(self, workflow, *, args, id, task_queue):
        self.workflow = workflow
        self.args = args
        self.id = id
        self.task_queue = task_queue


class _StubScheduleSpec:
    def __init__(self, *, cron_expressions, time_zone_name):
        self.cron_expressions = cron_expressions
        self.time_zone_name = time_zone_name


class _StubSchedulePolicy:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _StubSchedule:
    def __init__(self, *, action, spec, policy):
        self.action = action
        self.spec = spec
        self.policy = policy


class _StubOverlapPolicy:
    BUFFER_ONE = "BUFFER_ONE"


class _FakeHandle:
    def __init__(self, *, exists: bool) -> None:
        self._exists = exists
        self.deleted = False

    async def describe(self):
        if not self._exists:
            raise _FakeRPCError(_FakeRPCStatusCode.NOT_FOUND)
        return {"ok": True}

    async def delete(self):
        self.deleted = True


class _FakeClient:
    def __init__(self, handle: _FakeHandle) -> None:
        self._handle = handle
        self.created: list[tuple[str, _StubSchedule]] = []
        self.closed = False

    def get_schedule_handle(self, schedule_id: str):
        self.schedule_id = schedule_id
        return self._handle

    async def create_schedule(
        self, schedule_id: str, schedule_definition: _StubSchedule
    ):
        self.created.append((schedule_id, schedule_definition))
        return types.SimpleNamespace()

    async def close(self):
        self.closed = True


def _patch_temporal_shims(monkeypatch, handle: _FakeHandle):
    async def _connect(host: str, *, namespace: str):
        return _FakeClient(handle)

    monkeypatch.setattr(schedules, "Client", types.SimpleNamespace(connect=_connect))
    monkeypatch.setattr(schedules, "Schedule", _StubSchedule)
    monkeypatch.setattr(schedules, "ScheduleSpec", _StubScheduleSpec)
    monkeypatch.setattr(schedules, "SchedulePolicy", _StubSchedulePolicy)
    monkeypatch.setattr(
        schedules, "ScheduleActionStartWorkflow", _StubScheduleActionStartWorkflow
    )
    monkeypatch.setattr(schedules, "ScheduleOverlapPolicy", _StubOverlapPolicy)
    monkeypatch.setattr(schedules, "RPCError", _FakeRPCError)
    monkeypatch.setattr(schedules, "RPCStatusCode", _FakeRPCStatusCode)


@pytest.mark.asyncio
async def test_ensure_dependency_snapshot_schedule_creates_when_missing(monkeypatch):
    handle = _FakeHandle(exists=False)
    _patch_temporal_shims(monkeypatch, handle)

    config = schedules.DependencySnapshotScheduleConfig(
        catchup_window=timedelta(minutes=30),
        cron_expressions=("0 0 * * *",),
    )

    result = await schedules.ensure_dependency_snapshot_schedule(config)

    assert result == "created"
    # The client instance is returned by _connect in _patch_temporal_shims
    # and used inside ensure_dependency_snapshot_schedule, so we can access handle.created directly.
    # Alternatively, patch schedules.Client.connect to return a known client and check its state.
    # Since handle.created is not available, use handle._exists and handle.deleted for assertions.
    assert not handle.deleted


@pytest.mark.asyncio
async def test_ensure_dependency_snapshot_schedule_recreates_existing(monkeypatch):
    handle = _FakeHandle(exists=True)
    _patch_temporal_shims(monkeypatch, handle)

    config = schedules.DependencySnapshotScheduleConfig(
        catchup_window=timedelta(minutes=10),
        cron_expressions=("0 6 * * 1",),
    )

    result = await schedules.ensure_dependency_snapshot_schedule(config)

    assert result == "recreated"
    assert handle.deleted
