from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from prometheus.packaging import (
    OfflinePackagingConfig,
    OfflinePackagingOrchestrator,
    PackagingResult,
    load_config,
)
from prometheus.packaging.offline import (
    GIT_CORE_HOOKS_PATH_KEY,
    ContainerSettings,
    ModelSettings,
    PhaseResult,
)


def test_load_config_normalises_empty_token(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[models]
hf_token = ""
""".strip()
    )

    config = load_config(config_path)

    assert config.models.hf_token is None


def test_orchestrator_dry_run_creates_manifests(tmp_path: Path) -> None:
    repo_root = tmp_path
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # Stub scripts referenced by the orchestrator.
    for script in ("build-wheelhouse.sh", "download_models.py", "cleanup-macos-cruft.sh"):
        (scripts_dir / script).write_text("#!/bin/sh\n", encoding="utf-8")

    config = OfflinePackagingConfig(
        models=ModelSettings(spacy=["en_core_web_sm"]),
        containers=ContainerSettings(images=["example/image:1.0"]),
    )
    config.repo_root = repo_root

    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=repo_root, dry_run=True)
    result = orchestrator.run(
        only=["dependencies", "models", "containers", "checksums", "git"],
    )

    assert result.succeeded

    wheelhouse_manifest = repo_root / "vendor" / "wheelhouse" / "manifest.json"
    models_manifest = repo_root / "vendor" / "models" / "manifest.json"
    containers_manifest = repo_root / "vendor" / "images" / "manifest.json"
    checksum_file = repo_root / "vendor" / "CHECKSUMS.sha256"
    gitattributes = repo_root / ".gitattributes"

    for path in [
        wheelhouse_manifest,
        models_manifest,
        containers_manifest,
    ]:
        assert path.exists(), f"Expected {path} to be created"

    assert not checksum_file.exists(), "Dry-run should not write checksum file"
    assert not gitattributes.exists(), "Dry-run should not modify .gitattributes"

    manifest = json.loads(wheelhouse_manifest.read_text(encoding="utf-8"))
    assert manifest["extras"] == config.poetry.extras


def test_run_command_retries_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    config.commands.retries = 3
    config.commands.retry_backoff_seconds = 0.0
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    attempts: dict[str, int] = {"count": 0}

    def fake_run(
        command,
        *,
        cwd,
        check,
        env,
        capture_output,
        text,
    ):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise subprocess.CalledProcessError(1, command)
        stdout = "ok" if capture_output else None
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=None)

    monkeypatch.setattr(
        "prometheus.packaging.offline.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        "prometheus.packaging.offline.time.sleep",
        lambda _: None,
    )

    result = orchestrator._run_command(["echo", "ok"], "echo ok", capture_output=True)

    assert attempts["count"] == 2
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.stdout == "ok"


def test_run_command_retries_exhausted(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    config.commands.retries = 2
    config.commands.retry_backoff_seconds = 0.0
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    attempts: dict[str, int] = {"count": 0}

    def failing_run(
        command,
        *,
        cwd,
        check,
        env,
        capture_output,
        text,
    ):
        attempts["count"] += 1
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(
        "prometheus.packaging.offline.subprocess.run",
        failing_run,
    )
    monkeypatch.setattr(
        "prometheus.packaging.offline.time.sleep",
        lambda _: None,
    )

    with pytest.raises(subprocess.CalledProcessError):
        orchestrator._run_command(["false"], "always fails")

    assert attempts["count"] == 2


def test_lfs_install_hook_conflict(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    config.cleanup.lfs_paths = ["vendor/wheelhouse"]
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    vendor = tmp_path / "vendor" / "wheelhouse"
    vendor.mkdir(parents=True, exist_ok=True)

    original_which = shutil.which

    def fake_which(name: str) -> str | None:
        if name == "git-lfs":
            return "/usr/bin/git-lfs"
        return original_which(name)

    monkeypatch.setattr("prometheus.packaging.offline.shutil.which", fake_which)
    
    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        if command[:3] == ["git", "lfs", "install"]:
            raise subprocess.CalledProcessError(2, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    # Should not raise even though git lfs install reports existing hooks.
    orchestrator._ensure_lfs_checkout(config.cleanup.lfs_paths)


def test_dependencies_phase_uses_no_update_when_supported(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    calls: list[tuple[tuple[str, ...], str]] = []

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        calls.append((tuple(command), description))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_poetry_version",
        lambda self, binary: "1.8.3",
    )
    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    orchestrator._phase_dependencies()

    assert (config.poetry.binary, "lock", "--no-update") in [call[0] for call in calls]


def test_dependencies_phase_skips_no_update_for_poetry_v2(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    calls: list[tuple[tuple[str, ...], str]] = []

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        calls.append((tuple(command), description))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_poetry_version",
        lambda self, binary: "2.2.0",
    )
    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    orchestrator._phase_dependencies()

    lock_invocations = [call[0] for call in calls if call[1].startswith("poetry lock")]
    assert (config.poetry.binary, "lock") in lock_invocations
    assert all("--no-update" not in invocation for invocation in lock_invocations)


def test_dependencies_phase_retries_without_no_update(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    calls: list[tuple[tuple[str, ...], str]] = []

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        calls.append((tuple(command), description))
        if "--no-update" in command:
            raise subprocess.CalledProcessError(2, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_poetry_version",
        lambda self, binary: "1.8.0",
    )
    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    orchestrator._phase_dependencies()

    lock_invocations = [call[0] for call in calls if call[1].startswith("poetry lock")]
    assert (config.poetry.binary, "lock", "--no-update") in lock_invocations
    assert (config.poetry.binary, "lock") in lock_invocations


def test_dependency_update_check_writes_report(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    config.updates.enabled = True
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    outdated_payload = json.dumps(
        [
            {
                "name": "example",
                "version": "1.0.0",
                "latest_version": "2.0.0",
                "description": "Example package",
            },
            {
                "name": "helper",
                "version": "1.2.3",
                "latest_version": "1.3.0",
                "description": "Helper package",
            },
        ]
    )

    commands: list[tuple[tuple[str, ...], str, bool]] = []

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        commands.append((tuple(command), description, capture_output))
        if command[:3] == [
            config.poetry.binary,
            "show",
            "--outdated",
        ]:
            return subprocess.CompletedProcess(command, 0, stdout=outdated_payload, stderr="")
        stdout = "" if capture_output else None
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    orchestrator._phase_dependencies()

    assert commands, "Expected commands to be invoked"
    report_path = config.wheelhouse_dir / config.updates.report_filename
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(orchestrator._dependency_updates) == 2
    assert orchestrator._dependency_updates[0]["update_type"] == "major"
    assert orchestrator._dependency_updates[1]["update_type"] == "minor"
    assert report["updates"] == orchestrator._dependency_updates
    policy_snapshot = report["auto_update_policy"]
    assert policy_snapshot["enabled"] is False
    assert policy_snapshot["max_update_type"] == config.updates.auto.max_update_type
    assert policy_snapshot["allow"] == config.updates.auto.allow
    assert policy_snapshot["deny"] == config.updates.auto.deny
    assert policy_snapshot["max_batch"] == config.updates.auto.max_batch


def test_run_manifest_includes_auto_update_policy(tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    result = PackagingResult(
        succeeded=True,
        phase_results=[PhaseResult(name="dependencies", succeeded=True)],
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )

    orchestrator._write_run_manifest(result)

    manifest_path = (
        tmp_path
        / "vendor"
        / config.telemetry.manifest_filename
    )
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    policy_snapshot = manifest["auto_update_policy"]
    assert policy_snapshot["enabled"] is config.updates.auto.enabled
    assert policy_snapshot["max_update_type"] == config.updates.auto.max_update_type
    assert policy_snapshot["allow"] == config.updates.auto.allow
    assert policy_snapshot["deny"] == config.updates.auto.deny
    assert policy_snapshot["max_batch"] == config.updates.auto.max_batch


def test_auto_update_policy_applies_patch_upgrades(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    config.updates.enabled = True
    config.updates.auto.enabled = True
    config.updates.auto.max_update_type = "patch"
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    initial_payload = json.dumps(
        [
            {
                "name": "patchpkg",
                "version": "1.0.0",
                "latest_version": "1.0.1",
                "description": "Patch package",
            },
            {
                "name": "minorpkg",
                "version": "2.3.4",
                "latest_version": "2.4.0",
                "description": "Minor package",
            },
            {
                "name": "majorpkg",
                "version": "3.0.0",
                "latest_version": "4.0.0",
                "description": "Major package",
            },
        ]
    )
    post_update_payload = json.dumps(
        [
            {
                "name": "minorpkg",
                "version": "2.3.4",
                "latest_version": "2.4.0",
                "description": "Minor package",
            },
            {
                "name": "majorpkg",
                "version": "3.0.0",
                "latest_version": "4.0.0",
                "description": "Major package",
            },
        ]
    )

    state: dict[str, Any] = {"outdated_calls": 0, "update_commands": []}

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        if command[:3] == [config.poetry.binary, "show", "--outdated"]:
            state["outdated_calls"] += 1
            payload = initial_payload if state["outdated_calls"] == 1 else post_update_payload
            return subprocess.CompletedProcess(command, 0, stdout=payload, stderr="")
        if command[:2] == [config.poetry.binary, "update"]:
            state["update_commands"].append(tuple(command))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        stdout = "" if capture_output else None
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    orchestrator._phase_dependencies()

    assert state["outdated_calls"] == 2
    assert state["update_commands"] == [
        (config.poetry.binary, "update", "patchpkg"),
    ]

    summary = orchestrator.dependency_summary
    assert summary["has_updates"] is True
    assert summary["auto_applied"] == ["patchpkg"]
    assert summary["counts"]["patch"] == 0
    assert any(
        action.startswith("Run smoke tests after auto-applied updates:")
        for action in summary["next_actions"]
    )
    remaining_packages = {item["name"] for item in orchestrator.dependency_updates}
    assert remaining_packages == {"minorpkg", "majorpkg"}

def test_ensure_git_branch_handles_lfs_hook_exit(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    state = {"branch": "main", "checkout_attempts": 0}

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_git_current_branch",
        lambda self: state["branch"],
    )

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        if command[:3] == ["git", "checkout", "-B"]:
            state["checkout_attempts"] += 1
            state["branch"] = command[-1]
            raise subprocess.CalledProcessError(1, command)
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    orchestrator._ensure_git_branch("offline-packaging-auto")

    assert state["branch"] == "offline-packaging-auto"
    assert state["checkout_attempts"] == 1


def test_git_commit_retries_after_lfs_hook_error(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    state = {"commit_attempts": 0, "force_called": False}
    commands: list[tuple[tuple[str, ...], str, bool]] = []

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        commands.append((tuple(command), description, capture_output))
        if command[:2] == ["git", "commit"]:
            state["commit_attempts"] += 1
            if "retry" not in description:
                raise subprocess.CalledProcessError(
                    1,
                    command,
                    output="This should be run through Git's post-merge hook.\nRun `git lfs update` to install it.\n",
                )
            return subprocess.CompletedProcess(command, 0, stdout="commit ok", stderr="")
        if command == ["git", "lfs", "update"]:
            raise subprocess.CalledProcessError(
                2,
                command,
                stderr=(
                    "Hook already exists: pre-push\n"
                    "To resolve this, either:\n"
                    "  1: run `git lfs update --manual` for instructions on how to merge hooks.\n"
                    "  2: run `git lfs update --force` to overwrite your hook."
                ),
            )
        if command == ["git", "lfs", "update", "--force"]:
            state["force_called"] = True
            return subprocess.CompletedProcess(command, 0, stdout="update ok", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )
    monkeypatch.setattr(
        "prometheus.packaging.offline.shutil.which",
        lambda _: "/usr/bin/git-lfs",
    )

    orchestrator._git_commit(config.git, "offline-packaging-auto")

    assert state["commit_attempts"] == 2
    assert state["force_called"] is True
    first_commit = commands[0]
    assert first_commit[0][:2] == ("git", "commit")
    assert first_commit[2] is True


def test_git_commit_uses_hookspath_fallback(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    repo_hooks = tmp_path / ".git" / "hooks"
    repo_hooks.mkdir(parents=True, exist_ok=True)

    error_output = (
        "This should be run through Git's post-merge hook.\n"
        "Run `git lfs update` to install it.\n"
    )
    original_hooks = "/custom/trunk/hooks"

    state = {
        "commit_attempts": 0,
        "install_called": False,
        "config_commands": [],
    }
    commands: list[tuple[tuple[str, ...], str, bool]] = []

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        commands.append((tuple(command), description, capture_output))
        if command[:2] == ["git", "commit"]:
            state["commit_attempts"] += 1
            if state["commit_attempts"] < 3:
                raise subprocess.CalledProcessError(
                    1,
                    command,
                    output=error_output,
                    stderr=error_output,
                )
            return subprocess.CompletedProcess(command, 0, stdout="commit ok", stderr="")
        if command == ["git", "lfs", "update"]:
            raise subprocess.CalledProcessError(
                2,
                command,
                stderr="Hook already exists: pre-push",
            )
        if command == ["git", "lfs", "update", "--force"]:
            return subprocess.CompletedProcess(command, 0, stdout="update ok", stderr="")
        if command == ["git", "lfs", "install", "--local", "--force"]:
            state["install_called"] = True
            return subprocess.CompletedProcess(command, 0, stdout="install ok", stderr="")

        if command[:3] == ["git", "config", GIT_CORE_HOOKS_PATH_KEY]:
            state["config_commands"].append(tuple(command[3:]))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )
    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_git_get_hooks_path",
        lambda self: original_hooks,
    )
    monkeypatch.setattr(
        "prometheus.packaging.offline.shutil.which",
        lambda _: "/usr/bin/git-lfs",
    )

    orchestrator._git_commit(config.git, "offline-packaging-auto")

    assert state["commit_attempts"] == 3
    assert state["install_called"] is True
    repo_hooks_str = str(repo_hooks.resolve())
    assert state["config_commands"] == [(repo_hooks_str,), (original_hooks,)]
    fallback_calls = [call for call in commands if call[1] == "git commit offline artefacts (hooks fallback)"]
    assert fallback_calls, "Expected fallback commit to run"
    assert fallback_calls[-1][2] is True


def test_git_commit_propagates_non_lfs_error(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    def failing_run_command(self, command, description, *, env=None, capture_output=False):
        if command[:2] == ["git", "commit"]:
            raise subprocess.CalledProcessError(1, command, output="fatal: other failure")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        failing_run_command,
    )
    def unexpected_update(self) -> None:
        raise AssertionError("git lfs update should not run")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_ensure_git_lfs_update",
        unexpected_update,
    )

    with pytest.raises(subprocess.CalledProcessError):
        orchestrator._git_commit(config.git, "main")


def test_git_lfs_update_retries_with_force(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    calls: list[tuple[tuple[str, ...], str, bool]] = []

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        calls.append((tuple(command), description, capture_output))
        if command == ["git", "lfs", "update"]:
            raise subprocess.CalledProcessError(
                2,
                command,
                stderr="Hook already exists: pre-push\nrun `git lfs update --manual` to merge hooks.",
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )
    monkeypatch.setattr(
        "prometheus.packaging.offline.shutil.which",
        lambda _: "/usr/bin/git-lfs",
    )

    orchestrator._ensure_git_lfs_update()

    assert [call[0] for call in calls] == [
        ("git", "lfs", "update"),
        ("git", "lfs", "update", "--force"),
    ]
    assert all(call[2] is True for call in calls)
