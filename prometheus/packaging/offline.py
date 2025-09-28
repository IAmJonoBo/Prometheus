"""Offline packaging orchestrator for air-gapped environments."""

from __future__ import annotations

import copy
import fnmatch
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, is_dataclass
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
GIT_CORE_HOOKS_PATH_KEY = "core.hooksPath"
LFS_POINTER_SIGNATURE = b"version https://git-lfs.github.com/spec/v1"
VENDOR_WHEELHOUSE = "vendor/wheelhouse"
VENDOR_MODELS = "vendor/models"
VENDOR_IMAGES = "vendor/images"
DEPENDENCIES_UP_TO_DATE_MESSAGE = "All dependencies are up to date."


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
    lfs_paths: list[str] = field(default_factory=lambda: [VENDOR_WHEELHOUSE])
    ensure_lfs_hooks: bool = True
    normalize_symlinks: list[str] = field(
        default_factory=lambda: [
            VENDOR_MODELS,
        ]
    )


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
            f"{VENDOR_WHEELHOUSE}/** filter=lfs diff=lfs merge=lfs -text",
            f"{VENDOR_MODELS}/** filter=lfs diff=lfs merge=lfs -text",
            f"{VENDOR_IMAGES}/** filter=lfs diff=lfs merge=lfs -text",
        ]
    )
    pointer_check_paths: list[str] = field(
        default_factory=lambda: [
            VENDOR_WHEELHOUSE,
            VENDOR_MODELS,
            VENDOR_IMAGES,
        ]
    )


@dataclass
class TelemetrySettings:
    enabled: bool = True
    emit_run_manifest: bool = True
    manifest_filename: str = RUN_MANIFEST_FILENAME


@dataclass
class AutoUpdatePolicy:
    """Rules for automatically applying dependency updates."""

    enabled: bool = False
    max_update_type: str = "patch"
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    max_batch: int | None = None


@dataclass
class UpdateSettings:
    """Configuration for dependency update visibility."""

    enabled: bool = True
    include_dev: bool = True
    binary: str | None = None
    report_filename: str = "outdated-packages.json"
    auto: AutoUpdatePolicy = field(default_factory=AutoUpdatePolicy)


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
    updates: UpdateSettings = field(default_factory=UpdateSettings)
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
        current = getattr(instance, key)
        if is_dataclass(current) and isinstance(value, Mapping):
            _update_dataclass(current, value)
            continue
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
        self._dependency_updates: list[dict[str, Any]] = []
        self._reset_dependency_summary("Dependency check has not been executed yet")
        self._git_lfs_hooks_ensured = False
        self._symlink_replacements = 0
        self._pointer_scan_paths: list[str] = []

    @property
    def dependency_updates(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._dependency_updates)

    @property
    def dependency_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._dependency_summary)

    @property
    def symlink_replacements(self) -> int:
        return self._symlink_replacements

    @property
    def pointer_scan_paths(self) -> list[str]:
        return list(self._pointer_scan_paths)

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
        if settings.ensure_lfs_hooks:
            self._ensure_git_lfs_hooks()
        self._cleanup_remove_paths(settings.remove_paths)
        self._cleanup_reset_directories(settings)

        if settings.lfs_paths:
            self._ensure_lfs_checkout(settings.lfs_paths)
        if settings.normalize_symlinks:
            self._normalize_symlinks(settings.normalize_symlinks)

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
        self._check_dependency_updates()
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

        self._pointer_scan_paths = []
        if git_settings.pointer_check_paths:
            self._validate_lfs_materialisation(git_settings.pointer_check_paths)

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
        if not relative_paths:
            return
        if self.dry_run:
            LOGGER.info(
                "Dry-run: skipping git lfs checkout for %s",
                ", ".join(relative_paths),
            )
            return
        if not shutil.which("git-lfs"):
            LOGGER.warning("git-lfs binary not available; skipping pointer checkout")
            return

        self._ensure_git_lfs_hooks()

        for rel in relative_paths:
            rel_path = self.config.repo_root / rel
            if not rel_path.exists():
                LOGGER.debug("LFS path %s does not exist yet; skipping checkout", rel_path)
                continue
            self._run_command(["git", "lfs", "checkout", rel], f"git lfs checkout {rel}")

    def _ensure_git_lfs_hooks(self) -> None:
        if self._git_lfs_hooks_ensured:
            return
        if self.dry_run:
            LOGGER.info("Dry-run: would install git-lfs hooks locally")
            self._git_lfs_hooks_ensured = True
            return
        if not shutil.which("git-lfs"):
            LOGGER.warning("git-lfs binary not available; skipping git lfs install")
            self._git_lfs_hooks_ensured = True
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
        self._git_lfs_hooks_ensured = True

    def _normalize_symlinks(self, relative_roots: Sequence[str]) -> None:
        repo_root = self.config.repo_root.resolve()
        actual_replacements = 0
        planned_replacements = 0
        skipped: list[tuple[Path, str]] = []
        for candidate in self._iter_symlinks(relative_roots):
            target = self._resolve_symlink_target(candidate)
            skip_reason = self._symlink_skip_reason(target, repo_root)
            if skip_reason is not None:
                skipped.append((candidate, skip_reason))
                continue
            if self.dry_run:
                LOGGER.info("Dry-run: would replace symlink %s -> %s", candidate, target)
                planned_replacements += 1
                continue
            try:
                candidate.unlink()
                shutil.copy2(target, candidate)
                actual_replacements += 1
            except OSError as exc:  # pragma: no cover - filesystem race
                skipped.append((candidate, f"copy failed: {exc}"))
        if self.dry_run and planned_replacements:
            LOGGER.info(
                "Dry-run: would replace %d symlinks with real files",
                planned_replacements,
            )
        elif not self.dry_run and actual_replacements:
            LOGGER.info("Replaced %d symlinks with real files", actual_replacements)
        if not self.dry_run:
            self._symlink_replacements += actual_replacements
        for entry, reason in skipped:
            LOGGER.debug("Symlink %s skipped: %s", entry, reason)

    def _validate_lfs_materialisation(self, relative_roots: Sequence[str]) -> None:
        if self.dry_run:
            LOGGER.debug("Dry-run: skipping LFS pointer validation")
            return
        self._pointer_scan_paths = list(relative_roots)
        pointer_paths = self._collect_lfs_pointers(relative_roots)
        if pointer_paths:
            formatted = ", ".join(
                str(path.relative_to(self.config.repo_root)) for path in pointer_paths
            )
            raise RuntimeError(f"Detected git-lfs pointers that were not hydrated: {formatted}")

    def _collect_lfs_pointers(self, relative_roots: Sequence[str]) -> list[Path]:
        return [
            candidate
            for candidate in self._iter_files(relative_roots)
            if self._is_lfs_pointer(candidate)
        ]

    def _iter_symlinks(self, relative_roots: Sequence[str]) -> Iterator[Path]:
        for rel_root in relative_roots:
            root = (self.config.repo_root / rel_root).resolve()
            if not root.exists():
                LOGGER.debug("Symlink normalisation skipped missing root %s", root)
                continue
            yield from (candidate for candidate in root.rglob("*") if candidate.is_symlink())

    def _resolve_symlink_target(self, candidate: Path) -> Path:
        try:
            return candidate.resolve(strict=False)
        except OSError:  # pragma: no cover - filesystem race
            return candidate

    def _symlink_skip_reason(self, target: Path, repo_root: Path) -> str | None:
        try:
            target.relative_to(repo_root)
        except ValueError:
            return "outside repository"
        if not target.exists() and not self.dry_run:
            return "missing target"
        if target.exists() and target.is_dir():
            return "directory symlink"
        return None

    def _iter_files(self, relative_roots: Sequence[str]) -> Iterator[Path]:
        repo_root = self.config.repo_root.resolve()
        for rel_root in relative_roots:
            root = (self.config.repo_root / rel_root).resolve()
            if not root.exists():
                continue
            for candidate in root.rglob("*"):
                if not candidate.is_file():
                    continue
                try:
                    candidate.resolve().relative_to(repo_root)
                except ValueError:
                    continue
                yield candidate

    def _is_lfs_pointer(self, candidate: Path) -> bool:
        try:
            with candidate.open("rb") as handle:
                prefix = handle.read(len(LFS_POINTER_SIGNATURE))
        except OSError:  # pragma: no cover - filesystem race
            return False
        return prefix.startswith(LFS_POINTER_SIGNATURE)

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
            "dependency_updates": self._dependency_updates,
            "dependency_summary": self._dependency_summary,
            "auto_update_policy": self._auto_update_policy_snapshot(),
            "repository_hygiene": {
                "symlink_replacements": self._symlink_replacements,
                "pointer_scan_paths": list(self._pointer_scan_paths),
            },
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _auto_update_policy_snapshot(self) -> dict[str, Any]:
        policy = self.config.updates.auto
        return {
            "enabled": policy.enabled,
            "max_update_type": policy.max_update_type,
            "allow": list(policy.allow),
            "deny": list(policy.deny),
            "max_batch": policy.max_batch,
        }

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
                "%s already points to %s but git-lfs hooks still failed",
                GIT_CORE_HOOKS_PATH_KEY,
                repo_hooks,
            )
            return False

        LOGGER.warning(
            "Temporarily overriding %s to %s to reinstall git-lfs hooks",
            GIT_CORE_HOOKS_PATH_KEY,
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
                ["git", "config", "--path", GIT_CORE_HOOKS_PATH_KEY],
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
            ["git", "config", GIT_CORE_HOOKS_PATH_KEY, replacement],
            f"set temporary {GIT_CORE_HOOKS_PATH_KEY}",
        )
        try:
            yield
        finally:
            self._run_command(
                ["git", "config", GIT_CORE_HOOKS_PATH_KEY, original_path],
                f"restore original {GIT_CORE_HOOKS_PATH_KEY}",
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

    def _reset_dependency_summary(self, message: str) -> None:
        self._dependency_summary = {
            "counts": {"major": 0, "minor": 0, "patch": 0, "unknown": 0},
            "has_updates": False,
            "primary_recommendation": message,
            "next_actions": [],
            "auto_applied": [],
        }

    def _build_recommended_action(self, record: Mapping[str, Any]) -> str | None:
        name = record.get("name")
        update_type = record.get("update_type")
        current = record.get("current_version")
        latest = record.get("latest_version")
        if not name or not update_type:
            return None
        version_hint = f" ({current} → {latest})" if current and latest else ""
        if update_type == "major":
            return (
                f"Plan major upgrade for {name}{version_hint}: review release notes and run "
                "integration tests before promoting."
            )
        if update_type == "minor":
            return (
                f"Schedule minor upgrade for {name}{version_hint}: validate critical workflows "
                "during the next maintenance window."
            )
        if update_type == "patch":
            return (
                f"Apply patch update for {name}{version_hint} at the next opportunity to pick up "
                "bug fixes."
            )
        return f"Investigate update path for {name}{version_hint}; semver impact unknown."

    def _set_dependency_summary(
        self,
        *,
        message: str,
        actions: Sequence[str] | None = None,
        has_updates: bool | None = None,
    ) -> None:
        self._dependency_summary["primary_recommendation"] = message
        if has_updates is not None:
            self._dependency_summary["has_updates"] = has_updates
        if actions is not None:
            unique_actions: list[str] = []
            for action in actions:
                if action and action not in unique_actions:
                    unique_actions.append(action)
            self._dependency_summary["next_actions"] = unique_actions


    def _check_dependency_updates(self) -> None:
        settings = self.config.updates
        poetry_bin = settings.binary or self.config.poetry.binary
        has_updates = self._collect_dependency_updates(poetry_bin, settings)
        auto_applied: list[str] = []
        if has_updates:
            self._log_dependency_updates()
            auto_applied = self._auto_apply_dependency_updates(poetry_bin, settings)
            if auto_applied:
                has_updates = self._collect_dependency_updates(poetry_bin, settings)
                if has_updates:
                    self._log_dependency_updates()
        if auto_applied:
            self._annotate_auto_applied(auto_applied)
        self._write_dependency_update_report()

    def _collect_dependency_updates(
        self,
        poetry_bin: str,
        settings: UpdateSettings,
    ) -> bool:
        self._dependency_updates = []
        self._reset_dependency_summary("Dependency update check not executed")
        if not settings.enabled:
            LOGGER.info("Dependency update checks disabled; skipping")
            self._set_dependency_summary(
                message="Enable config.updates.enabled to surface dependency drift.",
                has_updates=False,
                actions=["Toggle config.updates.enabled to true and rerun packaging."],
            )
            return False
        if self.dry_run:
            LOGGER.info("Dry-run: skipping dependency update detection")
            self._set_dependency_summary(
                message="Dependency update detection skipped during dry-run.",
                has_updates=False,
            )
            return False
        command = [poetry_bin, "show", "--outdated", "--format", "json"]
        if not settings.include_dev:
            command.extend(["--only", "main"])
        try:
            result = self._run_command(command, "poetry show outdated", capture_output=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            message = f"Dependency update check failed: {exc}"
            LOGGER.warning(message)
            actions = [
                "Inspect poetry show --outdated logs and resolve the failure before packaging.",
            ]
            actions.extend(self._dependency_summary.get("next_actions", []))
            self._set_dependency_summary(
                message=message,
                has_updates=False,
                actions=actions,
            )
            return False
        if not result.stdout:
            LOGGER.info("poetry show --outdated produced no output")
            self._set_dependency_summary(
                message=DEPENDENCIES_UP_TO_DATE_MESSAGE,
                has_updates=False,
                actions=["No action required; dependency lockfile is current."],
            )
            return False
        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            message = f"Unable to parse poetry outdated output: {exc}"
            LOGGER.warning(message)
            actions = [
                "Investigate poetry show --outdated JSON output and re-run packaging.",
            ]
            actions.extend(self._dependency_summary.get("next_actions", []))
            self._set_dependency_summary(
                message=message,
                has_updates=False,
                actions=actions,
            )
            return False

        return self._process_dependency_entries(entries)

    def _auto_apply_dependency_updates(
        self,
        poetry_bin: str,
        settings: UpdateSettings,
    ) -> list[str]:
        policy = settings.auto
        if not policy.enabled:
            return []
        eligible = self._eligible_auto_update_packages(policy)
        if not eligible:
            LOGGER.info(
                "Auto-update policy enabled but no dependencies matched the configured criteria",
            )
            return []
        packages = [record["name"] for record in eligible if record.get("name")]
        unique_packages: list[str] = []
        for package in packages:
            if package not in unique_packages:
                unique_packages.append(package)
        packages = unique_packages
        if not packages:
            return []
        severities = sorted({record.get("update_type", "unknown") for record in eligible})
        LOGGER.info(
            "Automatically applying dependency updates (%s) for: %s",
            ", ".join(severities),
            ", ".join(packages),
        )
        if self.dry_run:
            LOGGER.info(
                "Dry-run: would execute poetry update for %s",
                ", ".join(packages),
            )
            return packages
        try:
            self._run_command(
                [poetry_bin, "update", *packages],
                f"poetry update {' '.join(packages)}",
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            LOGGER.warning("Automatic dependency update failed: %s", exc)
            actions = [
                "Inspect automatic dependency update logs and rerun packaging.",
            ]
            actions.extend(self._dependency_summary.get("next_actions", []))
            self._set_dependency_summary(
                message="Automatic dependency updates failed; manual intervention required.",
                actions=actions,
                has_updates=True,
            )
            return []
        return packages

    def _eligible_auto_update_packages(
        self,
        policy: AutoUpdatePolicy,
    ) -> list[dict[str, Any]]:
        if not self._dependency_updates:
            return []
        allow = {name.lower() for name in policy.allow}
        deny = {name.lower() for name in policy.deny}
        allowed_levels = self._allowed_update_levels(policy.max_update_type)
        candidates: list[dict[str, Any]] = []
        for record in self._dependency_updates:
            name = record.get("name")
            if not name:
                continue
            lowered = name.lower()
            if deny and lowered in deny:
                LOGGER.debug("Skipping %s due to deny list", name)
                continue
            if allow and lowered not in allow:
                continue
            update_type = record.get("update_type", "unknown")
            if update_type not in allowed_levels:
                continue
            candidates.append(record)
        if policy.max_batch is not None:
            if policy.max_batch <= 0:
                return []
            candidates = candidates[: policy.max_batch]
        return candidates

    def _allowed_update_levels(self, max_update_type: str) -> set[str]:
        ordered = ("patch", "minor", "major")
        if max_update_type == "unknown":
            return {"unknown", *ordered}
        try:
            index = ordered.index(max_update_type)
        except ValueError:
            index = 0
        return set(ordered[: index + 1])

    def _annotate_auto_applied(self, packages: Sequence[str]) -> None:
        if not packages:
            return
        unique: list[str] = []
        for name in packages:
            if name and name not in unique:
                unique.append(name)
        if not unique:
            return
        self._dependency_summary["auto_applied"] = unique
        follow_ups = [
            f"Run smoke tests after auto-applied updates: {', '.join(unique)}.",
        ]
        follow_ups.extend(self._dependency_summary.get("next_actions", []))
        self._set_dependency_summary(
            message=self._dependency_summary.get("primary_recommendation", ""),
            actions=follow_ups,
            has_updates=self._dependency_summary.get("has_updates", False),
        )
        if not self._dependency_summary.get("has_updates"):
            current_message = self._dependency_summary.get("primary_recommendation", "")
            if not current_message or current_message == DEPENDENCIES_UP_TO_DATE_MESSAGE:
                self._dependency_summary["primary_recommendation"] = (
                    "Auto-applied dependency updates during packaging."
                )

    def _process_dependency_entries(self, entries: Sequence[Mapping[str, Any]]) -> bool:
        counts = self._dependency_summary["counts"]
        actions: list[str] = []
        self._dependency_summary["next_actions"] = actions

        for entry in entries:
            record = self._build_dependency_record(entry)
            if not record:
                continue
            self._dependency_updates.append(record)
            key = record["update_type"] if record["update_type"] in counts else "unknown"
            counts[key] += 1
            recommendation = self._build_recommended_action(record)
            if recommendation:
                record["recommended_action"] = recommendation
                if recommendation not in actions:
                    actions.append(recommendation)

        if not self._dependency_updates:
            LOGGER.info("All dependencies are up to date")
            self._set_dependency_summary(
                message=DEPENDENCIES_UP_TO_DATE_MESSAGE,
                actions=["No action required; dependency lockfile is current."],
                has_updates=False,
            )
            return False

        self._dependency_summary["has_updates"] = True
        headline = self._dependency_headline(counts)
        self._dependency_summary["primary_recommendation"] = headline
        return True

    def _build_dependency_record(self, entry: Mapping[str, Any]) -> dict[str, Any] | None:
        name = entry.get("name")
        current = entry.get("version")
        latest = entry.get("latest_version")
        if not (name and current and latest):
            return None
        return {
            "name": name,
            "current_version": current,
            "latest_version": latest,
            "update_type": self._classify_update(current, latest),
            "description": entry.get("description"),
        }

    def _dependency_headline(self, counts: Mapping[str, int]) -> str:
        if counts["major"]:
            return "Prioritise resolving major dependency updates before the next release."
        if counts["minor"]:
            return "Schedule minor dependency updates in the upcoming maintenance window."
        if counts["patch"]:
            return "Apply available patch updates when convenient."
        return "Review dependency updates to determine next steps."

    def _log_dependency_updates(self) -> None:
        major = [item for item in self._dependency_updates if item["update_type"] == "major"]
        minor = [item for item in self._dependency_updates if item["update_type"] == "minor"]
        patch = [item for item in self._dependency_updates if item["update_type"] == "patch"]
        unknown = [item for item in self._dependency_updates if item["update_type"] == "unknown"]
        if major:
            LOGGER.warning(
                "%d dependencies have major updates available: %s",
                len(major),
                ", ".join(item["name"] for item in major),
            )
        if minor:
            LOGGER.info(
                "%d dependencies have minor updates available: %s",
                len(minor),
                ", ".join(item["name"] for item in minor),
            )
        if patch:
            LOGGER.info(
                "%d dependencies have patch updates available: %s",
                len(patch),
                ", ".join(item["name"] for item in patch),
            )
        if unknown:
            LOGGER.info(
                "%d dependencies have updates with unknown impact: %s",
                len(unknown),
                ", ".join(item["name"] for item in unknown),
            )

    def _write_dependency_update_report(self) -> None:
        if self.dry_run:
            return
        settings = self.config.updates
        target = self.config.wheelhouse_dir / settings.report_filename
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "updates": self._dependency_updates,
            "include_dev": settings.include_dev,
            "summary": self._dependency_summary,
            "auto_update_policy": self._auto_update_policy_snapshot(),
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _classify_update(self, current: str, latest: str) -> str:
        current_parts = self._version_components(current)
        latest_parts = self._version_components(latest)
        if not current_parts or not latest_parts:
            return "unknown"
        if latest_parts[0] > current_parts[0]:
            return "major"
        if latest_parts[1] > current_parts[1]:
            return "minor"
        if latest_parts[2] > current_parts[2]:
            return "patch"
        return "unknown"

    @staticmethod
    def _version_components(version: str) -> tuple[int, int, int] | None:
        numbers = re.findall(r"\d+", version)
        if not numbers:
            return None
        parts = [int(part) for part in numbers[:3]]
        while len(parts) < 3:
            parts.append(0)
        return parts[0], parts[1], parts[2]

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
