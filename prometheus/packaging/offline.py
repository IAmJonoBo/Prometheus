"""Offline packaging orchestrator for air-gapped environments."""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - defensive
    tomllib = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "defaults" / "offline_package.toml"
MANIFEST_FILENAME = "manifest.json"
RUN_MANIFEST_FILENAME = "packaging-run.json"
DRY_RUN_BRANCH_PLACEHOLDER = "<current>"


@dataclass
class PythonSettings:
    """Configuration for Python runtime checks."""

    expected_version: str = "3.11"
    ensure_uv: bool = True
    pip_min_version: str = "25.0"
    auto_upgrade_pip: bool = True


@dataclass
class PoetrySettings:
    """Configuration for dependency packaging."""

    binary: str = "poetry"
    lock: bool = True
    extras: list[str] = field(default_factory=lambda: ["pii"])
    include_dev: bool = True
    create_archive: bool = False
    min_version: str | None = None
    auto_install: bool = False
    self_update: bool = False


@dataclass
class ModelSettings:
    """Configuration for model artefact caching."""

    sentence_transformers: list[str] = field(
        default_factory=lambda: ["sentence-transformers/all-MiniLM-L6-v2"]
    )
    cross_encoders: list[str] = field(
        default_factory=lambda: ["cross-encoder/ms-marco-MiniLM-L-6-v2"]
    )
    spacy: list[str] = field(default_factory=lambda: ["en_core_web_lg"])
    skip_spacy: bool = False
    hf_token: str | None = None


@dataclass
class ContainerSettings:
    """Configuration for container image exports."""

    images: list[str] = field(
        default_factory=lambda: [
            "opensearchproject/opensearch:2.13.0",
            "qdrant/qdrant:v1.11.0",
            "temporalio/auto-setup:1.26",
        ]
    )
    skip_pull: bool = False


@dataclass
class CleanupSettings:
    """Configuration for repository hygiene before packaging."""

    enabled: bool = True
    reset_vendor: bool = False
    reset_directories: list[str] = field(
        default_factory=lambda: [
            "vendor/wheelhouse",
            "vendor/models",
            "vendor/images",
        ]
    )
    preserve_globs: list[str] = field(
        default_factory=lambda: [
            "vendor/wheelhouse/requirements.txt",
        ]
    )
    remove_paths: list[str] = field(
        default_factory=lambda: [
            "vendor/CHECKSUMS.sha256",
        ]
    )
    lfs_paths: list[str] = field(default_factory=lambda: ["vendor/wheelhouse"])


@dataclass
class GitSettings:
    """Configuration for repository hygiene."""

    update_gitattributes: bool = True
    commit: bool = False
    commit_message: str = "chore: refresh offline packaging artefacts"
    signoff: bool = False
    ensure_branch: str | None = None
    stage: list[str] = field(
        default_factory=lambda: [
            ".gitattributes",
            "configs/defaults/offline_package.toml",
            "docs/offline-packaging-orchestrator.md",
            "prometheus/packaging",
            "scripts/offline_package.py",
            "vendor",
        ]
    )
    push: bool = False
    remote: str = "origin"
    patterns: list[str] = field(
        default_factory=lambda: [
            "vendor/wheelhouse/** filter=lfs diff=lfs merge=lfs -text",
            "vendor/models/** filter=lfs diff=lfs merge=lfs -text",
            "vendor/images/**/*.tar filter=lfs diff=lfs merge=lfs -text",
        ]
    )


@dataclass
class TelemetrySettings:
    enabled: bool = True
    emit_run_manifest: bool = True
    manifest_filename: str = RUN_MANIFEST_FILENAME


@dataclass
class CommandSettings:
    retries: int = 1
    retry_backoff_seconds: float = 2.0


@dataclass
class OfflinePackagingConfig:
    """Aggregated configuration for the orchestrator."""

    python: PythonSettings = field(default_factory=PythonSettings)
    poetry: PoetrySettings = field(default_factory=PoetrySettings)
    models: ModelSettings = field(default_factory=ModelSettings)
    containers: ContainerSettings = field(default_factory=ContainerSettings)
    cleanup: CleanupSettings = field(default_factory=CleanupSettings)
    git: GitSettings = field(default_factory=GitSettings)
    telemetry: TelemetrySettings = field(default_factory=TelemetrySettings)
    commands: CommandSettings = field(default_factory=CommandSettings)
    repo_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    config_path: Path | None = None

    @property
    def wheelhouse_dir(self) -> Path:
        return self.repo_root / "vendor" / "wheelhouse"

    @property
    def models_dir(self) -> Path:
        return self.repo_root / "vendor" / "models"

    @property
    def images_dir(self) -> Path:
        return self.repo_root / "vendor" / "images"

    @property
    def checksum_path(self) -> Path:
        return self.repo_root / "vendor" / "CHECKSUMS.sha256"


@dataclass
class PhaseResult:
    name: str
    succeeded: bool
    detail: str | None = None


@dataclass
class PackagingResult:
    """Outcome of an orchestrator run."""

    succeeded: bool
    phase_results: list[PhaseResult]
    started_at: datetime
    finished_at: datetime

    @property
    def failed_phases(self) -> list[PhaseResult]:
        return [result for result in self.phase_results if not result.succeeded]

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


def _update_dataclass(instance: object, values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        if not hasattr(instance, key):
            raise ValueError(
                f"Unknown configuration key '{key}' for {type(instance).__name__}"
            )
        setattr(instance, key, value)


def load_config(config_path: Path | None = None) -> OfflinePackagingConfig:
    """Load orchestrator configuration from a TOML file."""

    config = OfflinePackagingConfig()
    path = (config_path or DEFAULT_CONFIG_PATH).resolve()
    if not path.exists():
        LOGGER.debug("Configuration file %s not found; using defaults", path)
        return config

    if tomllib is None:  # pragma: no cover - python < 3.11 safeguard
        raise RuntimeError("tomllib is required to parse configuration files")

    LOGGER.debug("Loading configuration from %s", path)
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    for section_name, values in data.items():
        if not hasattr(config, section_name):
            raise ValueError(f"Unknown configuration section '{section_name}'")
        section = getattr(config, section_name)
        if isinstance(values, Mapping):
            _update_dataclass(section, values)
        else:
            raise ValueError(
                f"Section '{section_name}' must be a table of key-value pairs"
            )

    if isinstance(config.models.hf_token, str) and not config.models.hf_token:
        config.models.hf_token = None

    config.config_path = path
    return config


class OfflinePackagingOrchestrator:
    """Drive the offline packaging workflow."""

    PHASES: tuple[str, ...] = (
        "cleanup",
        "environment",
        "dependencies",
        "models",
        "containers",
        "checksums",
        "git",
    )

    def __init__(
        self,
        config: OfflinePackagingConfig | None = None,
        *,
        repo_root: Path | None = None,
        dry_run: bool = False,
    ) -> None:
        self.config = config or load_config()
        if repo_root is not None:
            self.config.repo_root = repo_root
        self.dry_run = dry_run
        self._phase_results: list[PhaseResult] = []

    def run(
        self,
        *,
        only: Sequence[str] | None = None,
        skip: Iterable[str] | None = None,
    ) -> PackagingResult:
        """Execute the orchestrator across the chosen phases."""

        selected_phases = self._select_phases(only=only, skip=skip)
        LOGGER.info("Running offline packaging with phases: %s", ", ".join(selected_phases))
        self._phase_results.clear()
        started_at = datetime.now(UTC)

        for phase in selected_phases:
            handler = getattr(self, f"_phase_{phase}")
            LOGGER.info("Starting phase: %s", phase)
            try:
                handler()
            except Exception as exc:  # pragma: no cover - human-visible logging
                detail = f"{type(exc).__name__}: {exc}"
                LOGGER.exception("Phase %s failed", phase)
                self._phase_results.append(PhaseResult(phase, False, detail))
                break
            else:
                self._phase_results.append(PhaseResult(phase, True))

        succeeded = all(result.succeeded for result in self._phase_results)
        finished_at = datetime.now(UTC)
        result = PackagingResult(
            succeeded=succeeded,
            phase_results=list(self._phase_results),
            started_at=started_at,
            finished_at=finished_at,
        )
        self._write_run_manifest(result)
        return result

    # ------------------------------------------------------------------
    # Phase handlers
    # ------------------------------------------------------------------
    def _phase_cleanup(self) -> None:
        settings = self.config.cleanup
        if not settings.enabled:
            LOGGER.info("Cleanup disabled; skipping phase")
            return

        LOGGER.info("Preparing repository hygiene before packaging")
        self._cleanup_remove_paths(settings.remove_paths)
        self._cleanup_reset_directories(settings)

        if settings.lfs_paths:
            self._ensure_lfs_checkout(settings.lfs_paths)

    def _phase_environment(self) -> None:
        python_settings = self.config.python
        self._assert_python_version(python_settings.expected_version)
        if python_settings.auto_upgrade_pip:
            self._ensure_pip_version(python_settings.pip_min_version)
        self._verify_poetry()
        if self.config.containers.images:
            self._verify_docker()
        if python_settings.ensure_uv:
            self._ensure_binary("uv")
        if platform.system() == "Darwin":
            self._run_cleanup_script()

    def _phase_dependencies(self) -> None:
        poetry_settings = self.config.poetry
        if poetry_settings.lock:
            lock_command = [poetry_settings.binary, "lock"]
            use_no_update = self._poetry_supports_no_update(poetry_settings.binary)
            if use_no_update:
                lock_command.append("--no-update")
            try:
                self._run_command(lock_command, "poetry lock")
            except subprocess.CalledProcessError as exc:
                if use_no_update:
                    LOGGER.warning(
                        "poetry lock --no-update failed (%s); retrying without the flag",
                        exc,
                    )
                    self._run_command(
                        [poetry_settings.binary, "lock"],
                        "poetry lock (retry)",
                    )
                else:
                    raise
        env = os.environ.copy()
        if poetry_settings.extras:
            env["EXTRAS"] = ",".join(poetry_settings.extras)
        env["INCLUDE_DEV"] = "true" if poetry_settings.include_dev else "false"
        if poetry_settings.create_archive:
            env["CREATE_ARCHIVE"] = "true"
        env["POETRY"] = poetry_settings.binary
        script_path = self.config.repo_root / "scripts" / "build-wheelhouse.sh"
        self._run_command([str(script_path)], "build wheelhouse", env=env)
        self._write_wheelhouse_manifest()

    def _phase_models(self) -> None:
        model_settings = self.config.models
        env = os.environ.copy()
        model_root = self.config.models_dir
        hf_home = model_root / "hf"
        sentence_home = model_root / "sentence-transformers"
        spacy_home = model_root / "spacy"
        for directory in (hf_home, sentence_home, spacy_home):
            directory.mkdir(parents=True, exist_ok=True)
        env["HF_HOME"] = str(hf_home)
        env["SENTENCE_TRANSFORMERS_HOME"] = str(sentence_home)
        env["TRANSFORMERS_CACHE"] = str(hf_home)
        env["SPACY_HOME"] = str(spacy_home)
        if model_settings.hf_token:
            env["HUGGINGFACEHUB_API_TOKEN"] = model_settings.hf_token
        script_path = self.config.repo_root / "scripts" / "download_models.py"
        cmd = [sys.executable, str(script_path)]
        for name in model_settings.sentence_transformers:
            cmd.extend(["--sentence-transformer", name])
        for name in model_settings.cross_encoders:
            cmd.extend(["--cross-encoder", name])
        for name in model_settings.spacy:
            cmd.extend(["--spacy-model", name])
        if model_settings.skip_spacy:
            cmd.append("--skip-spacy")
        self._run_command(cmd, "download models", env=env)
        self._write_models_manifest(model_settings)

    def _phase_containers(self) -> None:
        containers = self.config.containers
        if not containers.images:
            LOGGER.info("No container images configured; skipping phase")
            return
        images_dir = self.config.images_dir
        images_dir.mkdir(parents=True, exist_ok=True)
        for image in containers.images:
            safe_name = image.replace("/", "-").replace(":", "-")
            target = images_dir / f"{safe_name}.tar"
            if not containers.skip_pull:
                self._run_command(["docker", "pull", image], f"pull {image}")
            self._run_command(
                ["docker", "save", "-o", str(target), image],
                f"save {image}",
            )
        self._write_containers_manifest(containers)

    def _phase_checksums(self) -> None:
        if self.dry_run:
            LOGGER.info("Dry-run: skipping checksum generation")
            return
        vendor_dir = self.config.repo_root / "vendor"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        checksum_path = self.config.checksum_path
        entries: list[str] = []
        for path in sorted(vendor_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name in {".DS_Store"} or path.name.startswith("._"):
                continue
            digest = self._sha256(path)
            rel = path.relative_to(self.config.repo_root)
            entries.append(f"{digest}  {rel.as_posix()}")
        checksum_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
        LOGGER.info("Wrote checksums for %d artefacts", len(entries))

    def _phase_git(self) -> None:
        git_settings = self.config.git
        missing = self._ensure_gitattributes_patterns(git_settings)

        if self.dry_run:
            self._log_git_plan(git_settings, missing)
            return

        branch = git_settings.ensure_branch
        if branch:
            self._ensure_git_branch(branch)
        current_branch = branch or self._git_current_branch()

        has_changes = self._apply_git_staging(git_settings)
        commit_performed, has_changes = self._maybe_commit(
            git_settings,
            current_branch,
            has_changes,
        )
        self._maybe_push(git_settings, current_branch, commit_performed, has_changes)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _cleanup_remove_paths(self, paths: Iterable[str]) -> None:
        for rel_path in paths:
            target = (self.config.repo_root / rel_path).resolve()
            if not target.exists():
                continue
            if self.dry_run:
                LOGGER.info("Dry-run: would remove %s", target)
                continue
            self._remove_path(target)

    def _cleanup_reset_directories(self, settings: CleanupSettings) -> None:
        for rel_dir in settings.reset_directories:
            directory = (self.config.repo_root / rel_dir).resolve()
            directory.mkdir(parents=True, exist_ok=True)
            if not settings.reset_vendor:
                continue
            for child in directory.iterdir():
                rel = child.relative_to(self.config.repo_root).as_posix()
                if any(fnmatch.fnmatch(rel, pattern) for pattern in settings.preserve_globs):
                    continue
                if self.dry_run:
                    LOGGER.info("Dry-run: would remove %s", child)
                    continue
                self._remove_path(child)

    def _remove_path(self, path: Path) -> None:
        repo_root = self.config.repo_root.resolve()
        resolved = path.resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Refusing to remove path outside repository: {resolved}") from exc
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def _ensure_lfs_checkout(self, relative_paths: Sequence[str]) -> None:
        if self.dry_run:
            LOGGER.info("Dry-run: skipping git lfs checkout for %s", ", ".join(relative_paths))
            return
        if not shutil.which("git-lfs"):
            LOGGER.warning("git-lfs binary not available; skipping pointer checkout")
            return
        try:
            self._run_command(["git", "lfs", "install", "--local"], "git lfs install")
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 2:
                LOGGER.warning(
                    "git lfs install reported existing hooks; skipping install. "
                    "Run 'git lfs update --manual' if hooks need reconciliation."
                )
            else:
                raise
        for rel in relative_paths:
            rel_path = self.config.repo_root / rel
            if not rel_path.exists():
                LOGGER.debug("LFS path %s does not exist yet; skipping checkout", rel_path)
                continue
            self._run_command(["git", "lfs", "checkout", rel], f"git lfs checkout {rel}")

    def _write_run_manifest(self, result: PackagingResult) -> None:
        telemetry = self.config.telemetry
        if self.dry_run or not telemetry.enabled or not telemetry.emit_run_manifest:
            return
        manifest_path = self.config.repo_root / "vendor" / telemetry.manifest_filename
        payload = {
            "succeeded": result.succeeded,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "duration_seconds": result.duration_seconds,
            "phases": [
                {
                    "name": phase.name,
                    "succeeded": phase.succeeded,
                    "detail": phase.detail,
                }
                for phase in result.phase_results
            ],
            "config_path": str(self.config.config_path) if self.config.config_path else None,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _ensure_gitattributes_patterns(self, git_settings: GitSettings) -> list[str]:
        if not git_settings.update_gitattributes:
            LOGGER.info("Git updates disabled; skipping .gitattributes edits")
            return []
        gitattributes_path = self.config.repo_root / ".gitattributes"
        content = ""
        existing: set[str] = set()
        if gitattributes_path.exists():
            content = gitattributes_path.read_text(encoding="utf-8")
            existing = {line.strip() for line in content.splitlines() if line.strip()}
        missing = [line for line in git_settings.patterns if line not in existing]
        if not missing:
            LOGGER.info(".gitattributes already tracks required patterns")
            return []
        if self.dry_run:
            return missing
        append_newline = bool(content and not content.endswith("\n"))
        with gitattributes_path.open("a", encoding="utf-8") as fh:
            if append_newline:
                fh.write("\n")
            for line in missing:
                fh.write(f"{line}\n")
        LOGGER.info("Appended %d patterns to .gitattributes", len(missing))
        return missing

    def _render_commit_message(self, template: str, branch: str) -> str:
        timestamp = datetime.now(UTC).isoformat()
        message = template.replace("{timestamp}", timestamp)
        return message.replace("{branch}", branch)

    def _log_git_plan(self, git_settings: GitSettings, missing: Sequence[str]) -> None:
        if missing:
            LOGGER.info(
                "Dry-run: would append %d patterns to .gitattributes",
                len(missing),
            )
        if git_settings.ensure_branch:
            LOGGER.info(
                "Dry-run: would ensure branch %s before staging",
                git_settings.ensure_branch,
            )
        if git_settings.stage:
            LOGGER.info(
                "Dry-run: would stage paths: %s",
                ", ".join(git_settings.stage),
            )
        if git_settings.commit:
            LOGGER.info(
                "Dry-run: would commit staged artefacts with message '%s'",
                self._render_commit_message(
                    git_settings.commit_message,
                    git_settings.ensure_branch or DRY_RUN_BRANCH_PLACEHOLDER,
                ),
            )
        if git_settings.push:
            LOGGER.info(
                "Dry-run: would push artefacts to %s/%s",
                git_settings.remote,
                git_settings.ensure_branch or DRY_RUN_BRANCH_PLACEHOLDER,
            )

    def _ensure_git_branch(self, branch: str) -> None:
        current = self._git_current_branch()
        if current == branch:
            LOGGER.debug("Already on branch %s", branch)
            return
        try:
            self._run_command(["git", "checkout", "-B", branch], f"git checkout -B {branch}")
        except subprocess.CalledProcessError as exc:
            new_branch = self._git_current_branch()
            if new_branch == branch:
                LOGGER.warning(
                    "git checkout -B %s reported exit code %s but branch is now active; continuing",
                    branch,
                    exc.returncode,
                )
                return
            raise

    def _git_current_branch(self) -> str:
        result = self._run_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            "git rev-parse --abbrev-ref HEAD",
            capture_output=True,
        )
        if not result.stdout:
            raise RuntimeError("Unable to determine current git branch")
        return result.stdout.strip()

    def _git_stage(self, patterns: Sequence[str]) -> None:
        command = ["git", "add", "--", *patterns]
        self._run_command(command, "git add staged artefacts")

    def _git_has_changes(self) -> bool:
        result = self._run_command(
            ["git", "status", "--porcelain"],
            "git status --porcelain",
            capture_output=True,
        )
        return bool(result.stdout.strip() if result.stdout is not None else "")

    def _git_commit(self, git_settings: GitSettings, branch: str) -> None:
        message = self._render_commit_message(git_settings.commit_message, branch)
        command = ["git", "commit", "-m", message]
        if git_settings.signoff:
            command.append("--signoff")
        try:
            self._run_command(command, "git commit offline artefacts", capture_output=True)
        except subprocess.CalledProcessError as exc:
            if not self._is_git_lfs_hook_error(exc):
                raise
            LOGGER.warning(
                "git commit failed because git-lfs hooks are missing; running git lfs update"
            )
            self._ensure_git_lfs_update()
            try:
                self._run_command(
                    command,
                    "git commit offline artefacts (retry)",
                    capture_output=True,
                )
            except subprocess.CalledProcessError as retry_exc:
                if not self._is_git_lfs_hook_error(retry_exc):
                    raise
                if not self._repair_git_hooks_and_commit(command):
                    raise

    def _git_push(self, git_settings: GitSettings, branch: str) -> None:
        command = ["git", "push", git_settings.remote, branch]
        self._run_command(command, f"git push to {git_settings.remote}/{branch}")

    def _apply_git_staging(self, git_settings: GitSettings) -> bool:
        if git_settings.stage:
            self._git_stage(git_settings.stage)
        else:
            LOGGER.debug("No git stage patterns configured; skipping git add")
        has_changes = self._git_has_changes()
        if not has_changes:
            LOGGER.info("No changes detected after staging")
        return has_changes

    def _maybe_commit(
        self,
        git_settings: GitSettings,
        branch: str,
        has_changes: bool,
    ) -> tuple[bool, bool]:
        if not git_settings.commit:
            return False, has_changes
        if not has_changes:
            LOGGER.info("Skipping commit because there are no staged changes")
            return False, has_changes
        self._git_commit(git_settings, branch)
        post_commit_changes = self._git_has_changes()
        if post_commit_changes:
            LOGGER.warning(
                "Changes remain after commit; inspect git status before pushing",
            )
        return True, post_commit_changes

    def _maybe_push(
        self,
        git_settings: GitSettings,
        branch: str,
        commit_performed: bool,
        has_changes: bool,
    ) -> None:
        if not git_settings.push:
            return
        if git_settings.commit and not commit_performed:
            LOGGER.info("Skipping push because commit was not executed")
            return
        if git_settings.commit and has_changes:
            LOGGER.info("Skipping push because changes remain staged after commit")
            return
        self._git_push(git_settings, branch)

    def _ensure_git_lfs_update(self) -> None:
        if not shutil.which("git-lfs"):
            LOGGER.warning("git-lfs binary not available; skipping git lfs update retry")
            return
        try:
            self._run_command(
                ["git", "lfs", "update"],
                "git lfs update",
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            if self._git_lfs_requires_force(exc):
                LOGGER.warning(
                    "git lfs update reported existing hooks; retrying with --force"
                )
                try:
                    self._run_command(
                        ["git", "lfs", "update", "--force"],
                        "git lfs update --force",
                        capture_output=True,
                    )
                except subprocess.CalledProcessError as force_exc:
                    LOGGER.warning(
                        "git lfs update --force failed (%s); continuing without retry",
                        force_exc,
                    )
            else:
                LOGGER.warning("git lfs update failed (%s); continuing without retry", exc)

    @staticmethod
    def _is_git_lfs_hook_error(exc: subprocess.CalledProcessError) -> bool:
        stdout = (exc.stdout or "").lower()
        stderr = (exc.stderr or "").lower()
        combined = f"{stdout}\n{stderr}"
        return "git lfs update" in combined and "post-merge hook" in combined

    @staticmethod
    def _git_lfs_requires_force(exc: subprocess.CalledProcessError) -> bool:
        stdout = (exc.stdout or "").lower()
        stderr = (exc.stderr or "").lower()
        combined = f"{stdout}\n{stderr}"
        return "hook already exists" in combined or "git lfs update --manual" in combined or "git lfs update --force" in combined

    def _repair_git_hooks_and_commit(self, command: Sequence[str]) -> bool:
        hooks_path = self._git_get_hooks_path()
        if not hooks_path:
            LOGGER.warning(
                "Unable to determine current git hooks path; skipping hooks fallback"
            )
            return False

        repo_hooks = (self.config.repo_root / ".git" / "hooks").resolve()
        try:
            current_path = Path(hooks_path).resolve()
        except OSError:
            current_path = Path(hooks_path)

        if current_path == repo_hooks:
            LOGGER.warning(
                "core.hooksPath already points to %s but git-lfs hooks still failed",
                repo_hooks,
            )
            return False

        LOGGER.warning(
            "Temporarily overriding core.hooksPath to %s to reinstall git-lfs hooks",
            repo_hooks,
        )

        with self._temporary_hooks_override(hooks_path, str(repo_hooks)):
            self._install_git_lfs_hooks()
            self._run_command(
                command,
                "git commit offline artefacts (hooks fallback)",
                capture_output=True,
            )
        return True

    def _git_get_hooks_path(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "config", "--path", "core.hooksPath"],
                cwd=self.config.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            return None
        value = result.stdout.strip() if result.stdout else ""
        return value or None

    def _install_git_lfs_hooks(self) -> None:
        if not shutil.which("git-lfs"):
            LOGGER.warning("git-lfs binary not available; skipping git lfs install fallback")
            return
        try:
            self._run_command(
                ["git", "lfs", "install", "--local", "--force"],
                "git lfs install --local --force",
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            LOGGER.warning(
                "git lfs install --local --force failed (%s); continuing without retry",
                exc,
            )

    @contextmanager
    def _temporary_hooks_override(self, original_path: str, replacement: str) -> Iterator[None]:
        self._run_command(
            ["git", "config", "core.hooksPath", replacement],
            "set temporary core.hooksPath",
        )
        try:
            yield
        finally:
            self._run_command(
                ["git", "config", "core.hooksPath", original_path],
                "restore original core.hooksPath",
            )

    def _ensure_poetry_binary(self) -> str:
        poetry_settings = self.config.poetry
        poetry_bin = poetry_settings.binary
        resolved = shutil.which(poetry_bin)
        if resolved:
            return resolved
        if not poetry_settings.auto_install:
            raise RuntimeError(
                f"Poetry binary '{poetry_bin}' not found in PATH. "
                "Enable auto_install or install poetry manually."
            )
        if self.dry_run:
            LOGGER.info("Dry-run: poetry binary missing; would install automatically")
            return poetry_bin
        self._run_command(
            [sys.executable, "-m", "pip", "install", "poetry"],
            "install poetry",
        )
        resolved_post = shutil.which(poetry_bin)
        if not resolved_post:
            raise RuntimeError("Poetry installation completed but binary still not found in PATH")
        return resolved_post

    def _poetry_version(self, poetry_bin: str) -> str | None:
        result = self._run_command([poetry_bin, "--version"], "poetry --version", capture_output=True)
        if not result.stdout:
            return None
        version = self._extract_version_token(result.stdout)
        if not version:
            LOGGER.debug("Unable to parse poetry version from output: %s", result.stdout)
        return version

    def _poetry_supports_no_update(self, poetry_bin: str) -> bool:
        version = self._poetry_version(poetry_bin)
        if version is None:
            LOGGER.debug("Poetry version unknown; defaulting to using --no-update flag")
            return True
        # Poetry 2.x removed the --no-update flag from `poetry lock`
        supports = self._compare_versions(version, "2.0.0") < 0
        if not supports:
            LOGGER.info(
                "Poetry %s does not support --no-update; lock command will run without it",
                version,
            )
        return supports

    def _maybe_upgrade_poetry(self, poetry_bin: str, version: str | None) -> None:
        settings = self.config.poetry
        target = settings.min_version
        if not target or not version:
            return
        if self._compare_versions(version, target) >= 0:
            LOGGER.info("Poetry version %s meets minimum %s", version, target)
            return
        if not settings.self_update:
            raise RuntimeError(
                f"Poetry {target} required but found {version}. Enable self_update or upgrade manually."
            )
        if self.dry_run:
            LOGGER.info(
                "Dry-run: would upgrade poetry from %s to >=%s",
                version,
                target,
            )
            return
        LOGGER.info("Upgrading poetry from %s to >=%s", version, target)
        self._run_command([poetry_bin, "self", "update"], "poetry self update")
        post_version = self._poetry_version(poetry_bin)
        if post_version and self._compare_versions(post_version, target) < 0:
            raise RuntimeError(
                f"Poetry upgrade did not reach required version {target}; detected {post_version}"
            )

    def _extract_version_token(self, text: str) -> str | None:
        cleaned = text.replace("(", " ").replace(")", " ")
        for token in cleaned.split():
            if token and token[0].isdigit():
                return token
        return None

    def _select_phases(
        self,
        *,
        only: Sequence[str] | None,
        skip: Iterable[str] | None,
    ) -> list[str]:
        available = list(self.PHASES)
        if only:
            invalid = [name for name in only if name not in available]
            if invalid:
                raise ValueError(f"Unknown phases in --only: {', '.join(invalid)}")
            selected = [name for name in available if name in set(only)]
        else:
            selected = available
        if skip:
            skip_set = set(skip)
            selected = [name for name in selected if name not in skip_set]
        return selected

    def _assert_python_version(self, expected: str) -> None:
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        if not current.startswith(expected):
            raise RuntimeError(
                f"Python {expected} is required; detected {current}. Configure pyenv/uv before running."
            )
        LOGGER.info("Python version %s satisfies expectation %s", current, expected)

    def _ensure_pip_version(self, minimum: str) -> None:
        if self.dry_run:
            LOGGER.info(
                "Dry-run: assuming pip satisfies minimum version %s",
                minimum,
            )
            return
        pip_version = self._get_pip_version()
        if self._compare_versions(pip_version, minimum) >= 0:
            LOGGER.info("pip version %s meets minimum %s", pip_version, minimum)
            return
        LOGGER.info("Upgrading pip from %s to >=%s", pip_version, minimum)
        self._run_command(
            [sys.executable, "-m", "pip", "install", f"pip>={minimum}"],
            "upgrade pip",
        )

    def _get_pip_version(self) -> str:
        result = self._run_command(
            [sys.executable, "-m", "pip", "--version"],
            "pip --version",
            capture_output=True,
        )
        if result.stdout is None:
            raise RuntimeError("pip --version produced no output")
        parts = result.stdout.split()
        for part in parts:
            if part and part[0].isdigit():
                return part
        raise RuntimeError(f"Unable to parse pip version from output: {result.stdout}")

    def _verify_poetry(self) -> None:
        poetry_bin = self._ensure_poetry_binary()
        version = self._poetry_version(poetry_bin)
        self._maybe_upgrade_poetry(poetry_bin, version)

    def _verify_docker(self) -> None:
        self._run_command(["docker", "--version"], "docker --version", capture_output=True)

    def _ensure_binary(self, binary: str) -> None:
        if shutil.which(binary):
            LOGGER.info("Found %s binary", binary)
            return
        LOGGER.warning("Binary '%s' not found in PATH", binary)

    def _run_cleanup_script(self) -> None:
        script = self.config.repo_root / "scripts" / "cleanup-macos-cruft.sh"
        if not script.exists():
            LOGGER.debug("Cleanup script %s missing; skipping", script)
            return
        self._run_command(["bash", str(script)], "cleanup macOS metadata")

    def _write_wheelhouse_manifest(self) -> None:
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "extras": self.config.poetry.extras,
            "include_dev": self.config.poetry.include_dev,
            "create_archive": self.config.poetry.create_archive,
            "commit": self._git_commit_hash(),
        }
        target = self.config.wheelhouse_dir / MANIFEST_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_models_manifest(self, models: ModelSettings) -> None:
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "sentence_transformers": models.sentence_transformers,
            "cross_encoders": models.cross_encoders,
            "spacy": models.spacy,
            "skip_spacy": models.skip_spacy,
        }
        target = self.config.models_dir / MANIFEST_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_containers_manifest(self, containers: ContainerSettings) -> None:
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "images": containers.images,
            "skip_pull": containers.skip_pull,
            "docker_version": self._get_docker_version(),
        }
        target = self.config.images_dir / MANIFEST_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _get_docker_version(self) -> str | None:
        try:
            result = self._run_command(
                ["docker", "--version"],
                "docker --version",
                capture_output=True,
            )
        except Exception:  # pragma: no cover - optional metadata
            return None
        return result.stdout.strip() if result.stdout else None

    def _git_commit_hash(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.config.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):  # pragma: no cover
            return None
        return result.stdout.strip()

    def _sha256(self, path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _run_command(
        self,
        command: Sequence[str],
        description: str,
        *,
        env: Mapping[str, str] | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess:
        LOGGER.debug("Running %s: %s", description, " ".join(command))
        if self.dry_run:
            LOGGER.info("Dry-run: skipping command %s", description)
            stdout: str | None = "" if capture_output else None
            stderr: str | None = "" if capture_output else None
            return subprocess.CompletedProcess(command, 0, stdout, stderr)

        attempts = max(1, self.config.commands.retries)
        backoff = max(0.0, self.config.commands.retry_backoff_seconds)
        env_vars = dict(os.environ, **env) if env else None

        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                result = subprocess.run(
                    command,
                    cwd=self.config.repo_root,
                    check=True,
                    env=env_vars,
                    capture_output=capture_output,
                    text=True,
                )
            except (subprocess.CalledProcessError, OSError) as exc:
                last_exc = exc
                should_retry = self._handle_command_failure(
                    exc,
                    description,
                    attempt,
                    attempts,
                    backoff,
                )
                if not should_retry:
                    break
            else:
                self._log_captured_output(
                    description,
                    getattr(result, "stdout", None),
                    getattr(result, "stderr", None),
                )
                return result

        assert last_exc is not None  # pragma: no cover - defensive
        raise last_exc

    def _handle_command_failure(
        self,
        exc: Exception,
        description: str,
        attempt: int,
        attempts: int,
        backoff: float,
    ) -> bool:
        if isinstance(exc, subprocess.CalledProcessError):
            self._log_captured_output(
                description,
                getattr(exc, "stdout", None),
                getattr(exc, "stderr", None),
            )
        if attempt >= attempts:
            LOGGER.error("Command %s failed after %d attempts", description, attempts)
            return False
        wait_time = backoff * attempt
        LOGGER.warning(
            "Command %s failed on attempt %d/%d: %s. Retrying in %.1fs",
            description,
            attempt,
            attempts,
            exc,
            wait_time,
        )
        if wait_time > 0:
            time.sleep(wait_time)
        return True

    @staticmethod
    def _log_captured_output(
        description: str,
        stdout: str | None,
        stderr: str | None,
    ) -> None:
        if stdout:
            LOGGER.debug("%s stdout:\n%s", description, stdout)
        if stderr:
            LOGGER.debug("%s stderr:\n%s", description, stderr)

    def _compare_versions(self, current: str, minimum: str) -> int:
        def _parts(version: str) -> list[int]:
            return [int(part) for part in version.split(".") if part.isdigit()]

        current_parts = _parts(current)
        minimum_parts = _parts(minimum)
        length = max(len(current_parts), len(minimum_parts))
        current_parts.extend([0] * (length - len(current_parts)))
        minimum_parts.extend([0] * (length - len(minimum_parts)))
        for cur, min_part in zip(current_parts, minimum_parts, strict=True):
            if cur > min_part:
                return 1
            if cur < min_part:
                return -1
        return 0


__all__ = [
    "OfflinePackagingConfig",
    "OfflinePackagingOrchestrator",
    "PackagingResult",
    "PhaseResult",
    "load_config",
]
