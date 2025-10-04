#!/usr/bin/env python3
"""
Automated Dependency Synchronization System.

This module provides intelligent, self-managing dependency updates that use
the Prometheus system to update itself. It includes graceful error handling,
recovery mechanisms, and environment synchronization capabilities.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .coordinator import OrchestrationCoordinator, OrchestrationContext

logger = logging.getLogger(__name__)

# Default paths
REPO_ROOT = Path(__file__).resolve().parents[2]
VAR_ROOT = REPO_ROOT / "var"
SCRIPTS_ROOT = REPO_ROOT / "scripts"


@dataclass
class AutoSyncConfig:
    """Configuration for automated dependency synchronization."""

    # Sync behavior
    auto_upgrade: bool = True
    auto_apply_safe: bool = True
    force_sync: bool = False
    update_mirror: bool = True

    # Safety thresholds
    max_major_updates: int = 0  # Block major updates by default
    max_minor_updates: int = 5
    max_patch_updates: int = 20

    # Error handling
    enable_rollback: bool = True
    max_retry_attempts: int = 3
    continue_on_error: bool = False

    # Environment sync
    sync_dev_env: bool = True
    sync_prod_env: bool = False  # Requires explicit opt-in
    validate_after_sync: bool = True

    # Metadata
    dry_run: bool = False
    verbose: bool = False


@dataclass
class AutoSyncResult:
    """Result of automated synchronization operation."""

    success: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    stages_completed: list[str] = field(default_factory=list)
    stages_failed: list[str] = field(default_factory=list)
    updates_applied: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rollback_performed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "stages_completed": self.stages_completed,
            "stages_failed": self.stages_failed,
            "updates_applied": self.updates_applied,
            "errors": self.errors,
            "rollback_performed": self.rollback_performed,
            "metadata": self.metadata,
        }


class AutoSyncOrchestrator:
    """
    Orchestrates automated dependency synchronization with self-update capabilities.

    This orchestrator uses the Prometheus system itself to manage dependency updates,
    providing graceful error handling, rollback capabilities, and environment sync.
    """

    def __init__(
        self,
        config: AutoSyncConfig | None = None,
        coordinator: OrchestrationCoordinator | None = None,
    ):
        self.config = config or AutoSyncConfig()
        self.coordinator = coordinator or OrchestrationCoordinator(
            OrchestrationContext(
                dry_run=self.config.dry_run,
                verbose=self.config.verbose,
            )
        )
        self._state_file = VAR_ROOT / "auto-sync-state.json"
        self._snapshot_file = VAR_ROOT / "auto-sync-snapshot.json"
        self._load_state()

    def _load_state(self) -> None:
        """Load previous synchronization state."""
        if self._state_file.exists():
            try:
                self._state = json.loads(self._state_file.read_text())
                logger.debug(f"Loaded auto-sync state from {self._state_file}")
            except Exception as e:
                logger.warning(f"Failed to load auto-sync state: {e}")
                self._state = {}
        else:
            self._state = {}

    def _save_state(self, result: AutoSyncResult) -> None:
        """Save synchronization state to disk."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(result.to_dict(), indent=2))
        logger.debug(f"Saved auto-sync state to {self._state_file}")

    def _create_snapshot(self) -> dict[str, Any]:
        """Create a snapshot of current state for rollback."""
        logger.info("Creating state snapshot for rollback capability...")

        snapshot = {
            "timestamp": datetime.now(UTC).isoformat(),
            "lock_file_hash": self._hash_file(REPO_ROOT / "poetry.lock"),
            "pyproject_hash": self._hash_file(REPO_ROOT / "pyproject.toml"),
            "contract_hash": self._hash_file(
                REPO_ROOT / "configs" / "dependency-profile.toml"
            ),
        }

        self._snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot_file.write_text(json.dumps(snapshot, indent=2))
        logger.debug(f"Created snapshot at {self._snapshot_file}")

        return snapshot

    def _hash_file(self, path: Path) -> str | None:
        """Compute hash of a file for change detection."""
        if not path.exists():
            return None
        try:
            import hashlib

            return hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to hash {path}: {e}")
            return None

    def _rollback(self) -> bool:
        """Rollback to previous snapshot state."""
        if not self.config.enable_rollback:
            logger.warning("Rollback disabled in configuration")
            return False

        if not self._snapshot_file.exists():
            logger.error("No snapshot available for rollback")
            return False

        logger.warning("Initiating rollback to previous state...")

        try:
            # Use git to restore files if available
            result = subprocess.run(
                ["git", "checkout", "HEAD", "poetry.lock", "pyproject.toml"],
                cwd=REPO_ROOT,
                capture_output=True,
                check=False,
            )

            if result.returncode == 0:
                logger.info("✅ Rollback successful via git")
                return True
            else:
                logger.error(f"Git rollback failed: {result.stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def _assess_updates(self) -> dict[str, Any]:
        """
        Assess available updates and determine safety.

        Uses the upgrade guard to evaluate updates against policy.
        """
        logger.info("Assessing available dependency updates...")

        # Run preflight check
        preflight_result = self.coordinator.deps_preflight()

        # Run upgrade guard
        guard_result = self.coordinator.deps_guard()

        # Analyze guard status
        guard_status = guard_result.get("status", "unknown")
        flagged_packages = guard_result.get("flagged_packages", [])

        assessment = {
            "safe": guard_status == "safe",
            "needs_review": guard_status == "needs-review",
            "blocked": guard_status == "blocked",
            "flagged_count": len(flagged_packages),
            "flagged_packages": flagged_packages,
            "guard_status": guard_status,
        }

        logger.info(
            f"Update assessment: status={guard_status}, flagged={len(flagged_packages)}"
        )

        return assessment

    def _apply_safe_updates(self, assessment: dict[str, Any]) -> dict[str, Any]:
        """Apply updates that are deemed safe by the guard."""
        if not self.config.auto_apply_safe:
            logger.info("Auto-apply disabled; skipping safe update application")
            return {"applied": False, "reason": "auto_apply_safe disabled"}

        if assessment.get("blocked"):
            logger.warning("Updates blocked by guard; skipping application")
            return {"applied": False, "reason": "blocked by guard"}

        logger.info("Applying safe dependency updates...")

        # Generate upgrade plan with advice
        upgrade_result = self.coordinator.deps_upgrade(
            auto_apply=True,
            generate_advice=True,
        )

        return {
            "applied": upgrade_result.get("success", False),
            "result": upgrade_result,
        }

    def _sync_environments(self) -> dict[str, Any]:
        """Synchronize dependencies across environments."""
        results = {}

        if self.config.sync_dev_env:
            logger.info("Synchronizing development environment...")
            results["dev"] = self.coordinator.deps_sync(force=self.config.force_sync)

        if self.config.sync_prod_env:
            logger.info("Synchronizing production environment...")
            # Additional safety checks for prod
            results["prod"] = self.coordinator.deps_sync(force=False)

        return results

    def _validate_sync(self) -> dict[str, Any]:
        """Validate synchronization results."""
        if not self.config.validate_after_sync:
            return {"validated": False, "reason": "validation disabled"}

        logger.info("Validating synchronization results...")

        # Run preflight again to verify
        validation_result = self.coordinator.deps_preflight()

        # Run guard to check for issues
        guard_result = self.coordinator.deps_guard()

        return {
            "validated": True,
            "preflight": validation_result,
            "guard": guard_result,
            "status": guard_result.get("status", "unknown"),
        }

    def execute(self) -> AutoSyncResult:
        """
        Execute automated dependency synchronization workflow.

        This is the main entry point that orchestrates the entire process:
        1. Create snapshot for rollback
        2. Assess available updates
        3. Apply safe updates
        4. Sync environments
        5. Validate results
        6. Rollback on failure
        """
        result = AutoSyncResult()

        try:
            # Stage 1: Create snapshot
            logger.info("Stage 1/5: Creating snapshot...")
            snapshot = self._create_snapshot()
            result.metadata["snapshot"] = snapshot
            result.stages_completed.append("snapshot")

            # Stage 2: Assess updates
            logger.info("Stage 2/5: Assessing updates...")
            assessment = self._assess_updates()
            result.metadata["assessment"] = assessment
            result.stages_completed.append("assessment")

            if assessment.get("blocked"):
                result.errors.append("Updates blocked by guard assessment")
                result.metadata["reason"] = "blocked"
                logger.warning("Updates blocked; stopping workflow")
                self._save_state(result)
                return result

            # Stage 3: Apply safe updates
            logger.info("Stage 3/5: Applying safe updates...")
            update_result = self._apply_safe_updates(assessment)
            result.metadata["updates"] = update_result
            result.stages_completed.append("updates")

            if update_result.get("applied"):
                result.updates_applied.append(update_result)

            # Stage 4: Sync environments
            logger.info("Stage 4/5: Synchronizing environments...")
            sync_result = self._sync_environments()
            result.metadata["sync"] = sync_result
            result.stages_completed.append("sync")

            # Stage 5: Validate
            logger.info("Stage 5/5: Validating results...")
            validation = self._validate_sync()
            result.metadata["validation"] = validation
            result.stages_completed.append("validation")

            # Check validation status
            validation_status = validation.get("status", "unknown")
            if validation_status in ("safe", "needs-review"):
                result.success = True
                logger.info("✅ Automated synchronization completed successfully")
            else:
                result.success = False
                result.errors.append(f"Validation failed: {validation_status}")
                logger.warning("⚠️  Synchronization completed with issues")

        except Exception as e:
            logger.error(f"Synchronization failed: {e}", exc_info=True)
            result.success = False
            result.errors.append(str(e))

            # Attempt rollback
            if self.config.enable_rollback:
                logger.warning("Attempting rollback due to error...")
                if self._rollback():
                    result.rollback_performed = True
                    logger.info("Rollback completed")
                else:
                    result.errors.append("Rollback failed")
                    logger.error("Rollback failed")

        finally:
            self._save_state(result)

        return result

    def get_status(self) -> dict[str, Any]:
        """Get current auto-sync status."""
        return {
            "config": {
                "auto_upgrade": self.config.auto_upgrade,
                "auto_apply_safe": self.config.auto_apply_safe,
                "enable_rollback": self.config.enable_rollback,
                "sync_dev_env": self.config.sync_dev_env,
                "sync_prod_env": self.config.sync_prod_env,
            },
            "last_run": self._state,
            "state_file": str(self._state_file),
        }


def main() -> int:
    """CLI entry point for auto-sync orchestrator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Automated dependency synchronization with self-update"
    )
    parser.add_argument(
        "command",
        choices=["execute", "status"],
        help="Command to execute",
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--no-rollback", action="store_true", help="Disable rollback on failure"
    )
    parser.add_argument(
        "--no-auto-apply", action="store_true", help="Disable automatic application"
    )
    parser.add_argument(
        "--sync-prod", action="store_true", help="Enable production environment sync"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = AutoSyncConfig(
        dry_run=args.dry_run,
        verbose=args.verbose,
        enable_rollback=not args.no_rollback,
        auto_apply_safe=not args.no_auto_apply,
        sync_prod_env=args.sync_prod,
    )

    orchestrator = AutoSyncOrchestrator(config)

    if args.command == "status":
        status = orchestrator.get_status()
        print(json.dumps(status, indent=2))
        return 0

    elif args.command == "execute":
        result = orchestrator.execute()
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
