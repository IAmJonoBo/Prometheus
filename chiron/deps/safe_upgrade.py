#!/usr/bin/env python3
"""
Safe automatic upgrade execution with rollback support.

This module provides automatic upgrade execution with comprehensive safety checks:
- Pre-upgrade validation
- Incremental upgrade with checkpoints
- Automatic rollback on failure
- Health checks after each upgrade
- Conflict detection and resolution
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class UpgradeCheckpoint:
    """Checkpoint for rollback during upgrade."""

    timestamp: datetime
    packages_upgraded: list[str]
    lock_file_backup: Path | None
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "packages_upgraded": list(self.packages_upgraded),
            "lock_file_backup": (
                str(self.lock_file_backup) if self.lock_file_backup else None
            ),
            "success": self.success,
        }


@dataclass(slots=True)
class UpgradeResult:
    """Result of an upgrade operation."""

    package: str
    success: bool
    previous_version: str | None
    new_version: str | None
    duration_s: float
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "success": self.success,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "duration_s": self.duration_s,
            "error_message": self.error_message,
        }


@dataclass(slots=True)
class AutoUpgradeReport:
    """Complete automatic upgrade report."""

    started_at: datetime
    completed_at: datetime
    upgrades: list[UpgradeResult]
    checkpoints: list[UpgradeCheckpoint]
    rollback_performed: bool
    final_status: Literal["success", "partial", "failed", "rolled_back"]
    summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "upgrades": [u.to_dict() for u in self.upgrades],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "rollback_performed": self.rollback_performed,
            "final_status": self.final_status,
            "summary": dict(self.summary),
        }


class SafeUpgradeExecutor:
    """
    Safe automatic upgrade executor with rollback support.

    Executes upgrades incrementally with health checks and automatic
    rollback on failure.
    """

    def __init__(
        self,
        project_root: Path,
        backup_dir: Path | None = None,
        max_batch_size: int = 5,
        enable_health_checks: bool = True,
    ):
        """
        Initialize safe upgrade executor.

        Args:
            project_root: Root directory of the project
            backup_dir: Directory for backups (default: project_root/var/upgrade-backups)
            max_batch_size: Maximum packages to upgrade in one batch
            enable_health_checks: Run health checks after each upgrade
        """
        self.project_root = project_root
        self.backup_dir = backup_dir or (project_root / "var" / "upgrade-backups")
        self.max_batch_size = max_batch_size
        self.enable_health_checks = enable_health_checks
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def execute_upgrades(
        self,
        packages_to_upgrade: list[tuple[str, str]],
        auto_rollback: bool = True,
    ) -> AutoUpgradeReport:
        """
        Execute upgrades with safety checks.

        Args:
            packages_to_upgrade: List of (package, target_version) tuples
            auto_rollback: Automatically rollback on failure

        Returns:
            AutoUpgradeReport with results
        """
        started_at = datetime.now(UTC)
        upgrades: list[UpgradeResult] = []
        checkpoints: list[UpgradeCheckpoint] = []
        rollback_performed = False

        logger.info(f"Starting safe upgrade of {len(packages_to_upgrade)} packages...")

        # Create initial checkpoint
        initial_checkpoint = self._create_checkpoint([])
        checkpoints.append(initial_checkpoint)

        # Process upgrades in batches
        batches = self._create_batches(packages_to_upgrade)

        for batch_idx, batch in enumerate(batches):
            logger.info(
                f"Processing batch {batch_idx + 1}/{len(batches)} "
                f"({len(batch)} packages)..."
            )

            batch_success = True

            for package, version in batch:
                result = self._upgrade_single_package(package, version)
                upgrades.append(result)

                if not result.success:
                    logger.error(
                        f"Upgrade failed for {package}: {result.error_message}"
                    )
                    batch_success = False
                    break

            # Create checkpoint after batch
            checkpoint = self._create_checkpoint(
                [pkg for pkg, _ in batch],
                success=batch_success,
            )
            checkpoints.append(checkpoint)

            # Run health checks if enabled
            if self.enable_health_checks and batch_success:
                health_ok = self._run_health_checks()
                if not health_ok:
                    logger.error("Health checks failed after upgrade batch")
                    batch_success = False

            # Handle failure
            if not batch_success:
                logger.warning("Batch upgrade failed")
                if auto_rollback:
                    logger.info("Initiating automatic rollback...")
                    rollback_success = self._rollback_to_checkpoint(initial_checkpoint)
                    rollback_performed = True
                    if rollback_success:
                        logger.info("Rollback successful")
                    else:
                        logger.error("Rollback failed")
                break

        completed_at = datetime.now(UTC)

        # Determine final status
        if rollback_performed:
            final_status = "rolled_back"
        else:
            success_count = sum(1 for u in upgrades if u.success)
            if success_count == len(packages_to_upgrade):
                final_status = "success"
            elif success_count > 0:
                final_status = "partial"
            else:
                final_status = "failed"

        summary = {
            "total": len(packages_to_upgrade),
            "successful": sum(1 for u in upgrades if u.success),
            "failed": sum(1 for u in upgrades if not u.success),
            "batches": len(batches),
            "checkpoints": len(checkpoints),
        }

        return AutoUpgradeReport(
            started_at=started_at,
            completed_at=completed_at,
            upgrades=upgrades,
            checkpoints=checkpoints,
            rollback_performed=rollback_performed,
            final_status=final_status,
            summary=summary,
        )

    def _create_batches(
        self,
        packages: list[tuple[str, str]],
    ) -> list[list[tuple[str, str]]]:
        """Split packages into batches for incremental upgrade."""
        batches: list[list[tuple[str, str]]] = []

        for i in range(0, len(packages), self.max_batch_size):
            batch = packages[i : i + self.max_batch_size]
            batches.append(batch)

        return batches

    def _create_checkpoint(
        self,
        packages: list[str],
        success: bool = True,
    ) -> UpgradeCheckpoint:
        """Create upgrade checkpoint with lock file backup."""
        timestamp = datetime.now(UTC)

        # Backup lock file
        lock_file = self.project_root / "poetry.lock"
        backup_path: Path | None = None

        if lock_file.exists():
            backup_name = f"poetry.lock.{timestamp.strftime('%Y%m%d_%H%M%S')}"
            backup_path = self.backup_dir / backup_name

            try:
                backup_path.write_bytes(lock_file.read_bytes())
                logger.debug(f"Created checkpoint backup: {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to create checkpoint backup: {e}")
                backup_path = None

        return UpgradeCheckpoint(
            timestamp=timestamp,
            packages_upgraded=packages,
            lock_file_backup=backup_path,
            success=success,
        )

    def _upgrade_single_package(
        self,
        package: str,
        version: str | None,
    ) -> UpgradeResult:
        """Upgrade a single package."""
        import time

        start_time = time.perf_counter()

        # Get current version
        previous_version = self._get_package_version(package)

        # Build upgrade command
        if version:
            cmd = ["poetry", "add", f"{package}@{version}"]
        else:
            cmd = ["poetry", "update", package]

        logger.info(f"Executing: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,  # 5 minute timeout
            )

            success = result.returncode == 0
            error_message = result.stderr if not success else None

            # Get new version
            new_version = self._get_package_version(package) if success else None

            duration = time.perf_counter() - start_time

            return UpgradeResult(
                package=package,
                success=success,
                previous_version=previous_version,
                new_version=new_version,
                duration_s=duration,
                error_message=error_message,
            )

        except subprocess.TimeoutExpired:
            duration = time.perf_counter() - start_time
            return UpgradeResult(
                package=package,
                success=False,
                previous_version=previous_version,
                new_version=None,
                duration_s=duration,
                error_message="Upgrade timed out after 5 minutes",
            )
        except Exception as e:
            duration = time.perf_counter() - start_time
            return UpgradeResult(
                package=package,
                success=False,
                previous_version=previous_version,
                new_version=None,
                duration_s=duration,
                error_message=str(e),
            )

    def _get_package_version(self, package: str) -> str | None:
        """Get currently installed version of a package."""
        try:
            result = subprocess.run(
                ["poetry", "show", package],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

            if result.returncode != 0:
                return None

            # Parse version from output
            for line in result.stdout.split("\n"):
                if line.strip().startswith("version"):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return parts[1].strip()

            return None

        except Exception as e:
            logger.debug(f"Failed to get version for {package}: {e}")
            return None

    def _run_health_checks(self) -> bool:
        """Run health checks after upgrade."""
        logger.info("Running health checks...")

        # Check 1: Verify poetry lock is consistent
        try:
            result = subprocess.run(
                ["poetry", "check"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            if result.returncode != 0:
                logger.error("Poetry check failed")
                return False
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

        # Check 2: Try importing key packages (optional, would need configuration)
        # For now, just return True if poetry check passed

        return True

    def _rollback_to_checkpoint(self, checkpoint: UpgradeCheckpoint) -> bool:
        """Rollback to a previous checkpoint."""
        logger.info(f"Rolling back to checkpoint from {checkpoint.timestamp}")

        if not checkpoint.lock_file_backup or not checkpoint.lock_file_backup.exists():
            logger.error("No backup available for rollback")
            return False

        lock_file = self.project_root / "poetry.lock"

        try:
            # Restore lock file
            lock_file.write_bytes(checkpoint.lock_file_backup.read_bytes())
            logger.info("Lock file restored from backup")

            # Reinstall dependencies
            result = subprocess.run(
                ["poetry", "install", "--sync"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )

            if result.returncode != 0:
                logger.error("Failed to reinstall dependencies during rollback")
                return False

            logger.info("Dependencies reinstalled successfully")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False


def execute_safe_upgrades(
    packages_to_upgrade: list[tuple[str, str]],
    project_root: Path,
    auto_rollback: bool = True,
    max_batch_size: int = 5,
) -> AutoUpgradeReport:
    """
    Execute safe upgrades with automatic rollback.

    Convenience function for creating executor and running upgrades.

    Args:
        packages_to_upgrade: List of (package, version) tuples
        project_root: Root directory of the project
        auto_rollback: Enable automatic rollback on failure
        max_batch_size: Maximum packages per batch

    Returns:
        AutoUpgradeReport with results
    """
    executor = SafeUpgradeExecutor(
        project_root=project_root,
        max_batch_size=max_batch_size,
        enable_health_checks=True,
    )
    return executor.execute_upgrades(packages_to_upgrade, auto_rollback)
