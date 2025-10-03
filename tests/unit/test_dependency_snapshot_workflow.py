from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import execution.workflows as workflows


class _StubGuard:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code

    def to_dict(self) -> dict[str, int]:
        return {"exit_code": self.exit_code}


class _StubPlanner:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code

    def to_dict(self) -> dict[str, int]:
        return {"exit_code": self.exit_code}


class _StubStatus:
    def __init__(self) -> None:
        self.generated_at = datetime.now(UTC)
        self.exit_code = 0
        self.summary = {
            "highest_severity": "needs-review",
            "recommended_commands": ["poetry update fastapi"],
        }
        self.guard = _StubGuard()
        self.planner = _StubPlanner()


def test_coerce_snapshot_request_handles_strings() -> None:
    request = workflows._coerce_snapshot_request(
        {
            "planner_packages": "fastapi, httpx ",
            "planner_enabled": "0",
            "planner_allow_major": "1",
            "planner_run_resolver": "True",
        }
    )

    assert request.planner_packages == ("fastapi", "httpx")
    assert request.planner_enabled is False
    assert request.planner_allow_major is True
    assert request.planner_run_resolver is True


def test_coerce_snapshot_request_handles_mixed_case_booleans() -> None:
    request = workflows._coerce_snapshot_request(
        {
            "planner_enabled": " YES ",
            "planner_allow_major": "fAlSe",
            "planner_run_resolver": "TrUe",
        }
    )

    assert request.planner_enabled is True
    assert request.planner_allow_major is False
    assert request.planner_run_resolver is True


@pytest.mark.parametrize("severity, delivered", [("critical", True), ("ok", False)])
@pytest.mark.asyncio
async def test_notify_dependency_snapshot_activity_threshold(
    tmp_path: Path,
    severity: str,
    delivered: bool,
) -> None:
    notification = workflows.DependencySnapshotNotification(
        channel="file",
        path=str(tmp_path / "notice.json"),
        severity_threshold="needs-review",
    )

    snapshot = {
        "summary": {"highest_severity": severity},
        "exit_code": 1,
    }

    result = await workflows.notify_dependency_snapshot_activity(snapshot, notification)

    assert result["delivered"] is delivered
    if delivered:
        assert Path(result["path"]).exists()
    else:
        assert not (tmp_path / "notice.json").exists()


@pytest.mark.asyncio
async def test_notify_dependency_snapshot_activity_with_invalid_threshold(
    tmp_path: Path,
) -> None:
    notification = workflows.DependencySnapshotNotification(
        channel="file",
        path=str(tmp_path / "notice.json"),
        severity_threshold="not-a-real-level",
    )

    snapshot = {
        "summary": {"highest_severity": "critical"},
        "exit_code": 2,
    }

    result = await workflows.notify_dependency_snapshot_activity(snapshot, notification)

    assert result["delivered"] is True
    assert Path(result["path"]).exists()


@pytest.mark.asyncio
async def test_run_dependency_snapshot_activity_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "snapshot.json"

    stub_status = _StubStatus()

    monkeypatch.setattr("scripts.deps_status.generate_status", lambda **_: stub_status)

    request = workflows.DependencySnapshotRequest(
        report_path=str(report_path),
        planner_packages=("fastapi",),
        planner_run_resolver=True,
    )

    result = await workflows.run_dependency_snapshot_activity(request)

    assert result["exit_code"] == 0
    assert result["summary"]["highest_severity"] == "needs-review"
    assert report_path.exists()
    payload = report_path.read_text(encoding="utf-8")
    assert "poetry update fastapi" in payload


@pytest.mark.asyncio
async def test_run_dependency_snapshot_activity_failure_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "snapshot.json"

    stub_status = _StubStatus()
    stub_status.exit_code = 2
    stub_status.summary["highest_severity"] = "critical"

    monkeypatch.setattr("scripts.deps_status.generate_status", lambda **_: stub_status)

    request = workflows.DependencySnapshotRequest(
        report_path=str(report_path),
        planner_packages=("fastapi",),
        planner_run_resolver=False,
    )

    result = await workflows.run_dependency_snapshot_activity(request)

    assert result["exit_code"] == 2
    assert result["summary"]["highest_severity"] == "critical"
    assert report_path.exists()
