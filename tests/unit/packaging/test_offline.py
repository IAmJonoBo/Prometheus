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
    GIT_LFS_HOOKS,
    LFS_POINTER_SIGNATURE,
    VENDOR_MODELS,
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
    for script in (
        "build-wheelhouse.sh",
        "download_models.py",
        "cleanup-macos-cruft.sh",
    ):
        (scripts_dir / script).write_text("#!/bin/sh\n", encoding="utf-8")

    config = OfflinePackagingConfig(
        models=ModelSettings(spacy=["en_core_web_sm"]),
        containers=ContainerSettings(images=["example/image:1.0"]),
    )
    config.repo_root = repo_root

    orchestrator = OfflinePackagingOrchestrator(
        config=config, repo_root=repo_root, dry_run=True
    )
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
        # trunk-ignore(bandit/B101)
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


def test_repair_git_lfs_hooks_rewrites_incorrect_scripts(
    monkeypatch, tmp_path: Path
) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    hooks_dir = tmp_path / "trunk-hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    bad_script = '#!/bin/sh\ngit lfs pre-push "$@"\n'
    shared_target = hooks_dir / "trunk-hook.sh"
    shared_target.write_text(bad_script)
    for hook in GIT_LFS_HOOKS:
        (hooks_dir / hook).symlink_to(shared_target)
    stray_hook = hooks_dir / "pre-commit"
    stray_hook.write_text(bad_script, encoding="utf-8")

    original_which = shutil.which

    def fake_which(name: str) -> str | None:
        if name == "git-lfs":
            return "/usr/bin/git-lfs"
        return original_which(name)

    def fake_run_command(self, command, description, *, env=None, capture_output=False):
        if command[:3] == ["git", "lfs", "install"]:
            return subprocess.CompletedProcess(command, 0)
        if command[:3] == ["git", "config", "--path"]:
            stdout = str(hooks_dir) if capture_output else None
            return subprocess.CompletedProcess(command, 0, stdout, None)
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr("prometheus.packaging.offline.shutil.which", fake_which)
    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_run_command",
        fake_run_command,
    )

    orchestrator._ensure_git_lfs_hooks()

    assert orchestrator.git_hooks_path == hooks_dir.resolve()
    assert set(orchestrator.hook_repairs) == set(GIT_LFS_HOOKS)
    assert orchestrator.hook_removals == ["pre-commit"]
    for hook in GIT_LFS_HOOKS:
        hook_path = hooks_dir / hook
        assert not hook_path.is_symlink()
        content = hook_path.read_text(encoding="utf-8")
        assert f"git lfs {hook}" in content
        assert f"'{hook}' file" in content
    assert not stray_hook.exists()


def test_normalize_symlinks_replaces_file_links(tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    models_dir = tmp_path / VENDOR_MODELS
    models_dir.mkdir(parents=True, exist_ok=True)
    source_file = models_dir / "source.bin"
    source_file.write_bytes(b"payload")
    symlink_path = models_dir / "link.bin"

    try:
        symlink_path.symlink_to(source_file)
    except (NotImplementedError, OSError):  # pragma: no cover - platform restriction
        pytest.skip("symlinks not supported on this platform")

    orchestrator._normalize_symlinks([VENDOR_MODELS])

    assert not symlink_path.is_symlink()
    assert symlink_path.read_bytes() == source_file.read_bytes()


def test_cleanup_metadata_removes_known_cruft(tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    wheelhouse_dir = tmp_path / "vendor" / "wheelhouse"
    wheelhouse_dir.mkdir(parents=True, exist_ok=True)
    healthy_wheel = wheelhouse_dir / "package.whl"
    healthy_wheel.write_text("artifact", encoding="utf-8")
    ds_store = wheelhouse_dir / ".DS_Store"
    ds_store.write_text("junk", encoding="utf-8")
    apple_double = wheelhouse_dir / "._package.whl"
    apple_double.write_text("junk", encoding="utf-8")

    orchestrator._cleanup_metadata(config.cleanup, include_script=False)

    assert healthy_wheel.exists()
    assert not ds_store.exists()
    assert not apple_double.exists()


def test_audit_wheelhouse_removes_orphans(tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    wheelhouse_dir = tmp_path / "vendor" / "wheelhouse"
    wheelhouse_dir.mkdir(parents=True, exist_ok=True)
    (wheelhouse_dir / "requirements.txt").write_text(
        "requests==2.31.0\n",
        encoding="utf-8",
    )
    kept = wheelhouse_dir / "requests-2.31.0-py3-none-any.whl"
    kept.write_text("wheel", encoding="utf-8")
    orphan = wheelhouse_dir / "unused-1.0.0-py3-none-any.whl"
    orphan.write_text("orphan", encoding="utf-8")

    orchestrator._audit_wheelhouse(remove_orphans=True)

    audit = orchestrator.wheelhouse_audit
    assert not orphan.exists()
    assert kept.exists()
    assert audit["status"] == "ok"
    assert not audit["missing_requirements"]
    assert "unused-1.0.0-py3-none-any.whl" in audit["removed_orphans"]
    assert not audit["orphan_artefacts"]


def test_audit_wheelhouse_reports_missing(tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(
        config=config, repo_root=tmp_path, dry_run=True
    )

    wheelhouse_dir = tmp_path / "vendor" / "wheelhouse"
    wheelhouse_dir.mkdir(parents=True, exist_ok=True)
    (wheelhouse_dir / "requirements.txt").write_text(
        "numpy==1.26.4\n",
        encoding="utf-8",
    )

    orchestrator._audit_wheelhouse(remove_orphans=False)

    audit = orchestrator.wheelhouse_audit
    assert audit["status"] == "attention"
    assert audit["missing_requirements"] == ["numpy==1.26.4"]
    assert audit["orphan_artefacts"] == []


def test_doctor_collects_diagnostics(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    config.containers.images = []
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    wheelhouse_dir = tmp_path / "vendor" / "wheelhouse"
    wheelhouse_dir.mkdir(parents=True, exist_ok=True)
    (wheelhouse_dir / "requirements.txt").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_get_pip_version",
        lambda self: "25.0",
    )
    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_poetry_version",
        lambda self, binary: "1.8.3",
    )
    monkeypatch.setattr(
        OfflinePackagingOrchestrator,
        "_get_docker_version",
        lambda self: None,
    )

    original_which = shutil.which

    def fake_which(binary: str) -> str | None:
        if binary == config.poetry.binary:
            return f"/usr/bin/{binary}"
        if binary == "docker":
            return None
        return original_which(binary)

    monkeypatch.setattr("prometheus.packaging.offline.shutil.which", fake_which)

    diagnostics = orchestrator.doctor()

    assert diagnostics["python"]["status"] in {"ok", "warning"}
    assert diagnostics["pip"]["version"] == "25.0"
    assert diagnostics["poetry"]["version"] == "1.8.3"
    assert diagnostics["docker"]["status"] == "skipped"
    assert diagnostics["wheelhouse"]["status"] == "ok"


def test_validate_lfs_materialisation_detects_pointers(tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    models_dir = tmp_path / VENDOR_MODELS
    models_dir.mkdir(parents=True, exist_ok=True)
    pointer_file = models_dir / "model.bin"
    pointer_file.write_bytes(LFS_POINTER_SIGNATURE + b"\nsize 123\n")

    with pytest.raises(RuntimeError) as excinfo:
        orchestrator._validate_lfs_materialisation([VENDOR_MODELS])

    assert "model.bin" in str(excinfo.value)


def test_validate_lfs_materialisation_dry_run_skips(tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(
        config=config, repo_root=tmp_path, dry_run=True
    )

    models_dir = tmp_path / VENDOR_MODELS
    models_dir.mkdir(parents=True, exist_ok=True)
    pointer_file = models_dir / "model.bin"
    pointer_file.write_bytes(LFS_POINTER_SIGNATURE + b"\nsize 123\n")

    orchestrator._validate_lfs_materialisation([VENDOR_MODELS])


def test_dependencies_phase_uses_no_update_when_supported(
    monkeypatch, tmp_path: Path
) -> None:
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


def test_dependencies_phase_skips_no_update_for_poetry_v2(
    monkeypatch, tmp_path: Path
) -> None:
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


def test_dependencies_phase_retries_without_no_update(
    monkeypatch, tmp_path: Path
) -> None:
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
            return subprocess.CompletedProcess(
                command, 0, stdout=outdated_payload, stderr=""
            )
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

    manifest_path = tmp_path / "vendor" / config.telemetry.manifest_filename
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    policy_snapshot = manifest["auto_update_policy"]
    assert policy_snapshot["enabled"] is config.updates.auto.enabled
    assert policy_snapshot["max_update_type"] == config.updates.auto.max_update_type
    assert policy_snapshot["allow"] == config.updates.auto.allow
    assert policy_snapshot["deny"] == config.updates.auto.deny
    assert policy_snapshot["max_batch"] == config.updates.auto.max_batch
    hygiene = manifest["repository_hygiene"]
    assert hygiene["symlink_replacements"] == 0
    assert hygiene["pointer_scan_paths"] == []
    assert hygiene["git_hooks_path"] is None
    assert hygiene["lfs_hook_repairs"] == []


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
            payload = (
                initial_payload if state["outdated_calls"] == 1 else post_update_payload
            )
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
            return subprocess.CompletedProcess(
                command, 0, stdout="commit ok", stderr=""
            )
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
            return subprocess.CompletedProcess(
                command, 0, stdout="update ok", stderr=""
            )
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
            return subprocess.CompletedProcess(
                command, 0, stdout="commit ok", stderr=""
            )
        if command == ["git", "lfs", "update"]:
            raise subprocess.CalledProcessError(
                2,
                command,
                stderr="Hook already exists: pre-push",
            )
        if command == ["git", "lfs", "update", "--force"]:
            return subprocess.CompletedProcess(
                command, 0, stdout="update ok", stderr=""
            )
        if command == ["git", "lfs", "install", "--local", "--force"]:
            state["install_called"] = True
            return subprocess.CompletedProcess(
                command, 0, stdout="install ok", stderr=""
            )

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
    fallback_calls = [
        call
        for call in commands
        if call[1] == "git commit offline artefacts (hooks fallback)"
    ]
    assert fallback_calls, "Expected fallback commit to run"
    assert fallback_calls[-1][2] is True


def test_git_commit_propagates_non_lfs_error(monkeypatch, tmp_path: Path) -> None:
    config = OfflinePackagingConfig()
    config.repo_root = tmp_path
    orchestrator = OfflinePackagingOrchestrator(config=config, repo_root=tmp_path)

    def failing_run_command(
        self, command, description, *, env=None, capture_output=False
    ):
        if command[:2] == ["git", "commit"]:
            raise subprocess.CalledProcessError(
                1, command, output="fatal: other failure"
            )
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


def test_load_config_with_performance_settings(tmp_path: Path) -> None:
    """Test that PerformanceSettings can be loaded from configuration."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[performance]
parallel_downloads = 8
lfs_batch_size = 200
lfs_timeout = 600
lfs_concurrent_transfers = 16
prefer_binary_wheels = false
wheel_cache_enabled = false
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.performance.parallel_downloads == 8
    assert config.performance.lfs_batch_size == 200
    assert config.performance.lfs_timeout == 600
    assert config.performance.lfs_concurrent_transfers == 16
    assert config.performance.prefer_binary_wheels is False
    assert config.performance.wheel_cache_enabled is False


def test_performance_settings_defaults() -> None:
    """Test that PerformanceSettings has correct defaults."""
    config = OfflinePackagingConfig()

    assert config.performance.parallel_downloads == 4
    assert config.performance.lfs_batch_size == 100
    assert config.performance.lfs_timeout == 300
    assert config.performance.lfs_concurrent_transfers == 8
    assert config.performance.prefer_binary_wheels is True
    assert config.performance.wheel_cache_enabled is True
