#!/usr/bin/env python3
"""
Automated remediation engine for common Chiron failures.

This module provides intelligent auto-fixes for:
- Dependency sync failures
- Wheelhouse build errors
- Mirror corruption
- Artifact validation failures
- Configuration drift
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class RemediationAction:
    """A single remediation action that can be applied."""

    action_type: Literal["command", "file_edit", "manual"]
    description: str
    command: list[str] | None = None
    file_path: Path | None = None
    file_content: str | None = None
    confidence: float = 1.0
    auto_apply: bool = False
    rollback_command: list[str] | None = None


@dataclass
class RemediationResult:
    """Result of applying remediation actions."""

    success: bool
    actions_applied: list[str]
    actions_failed: list[str]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class AutoRemediator:
    """
    Intelligent autoremediation engine for common Chiron failures.

    This class analyzes failure patterns and applies fixes automatically
    when confidence is high, or suggests manual actions otherwise.
    """

    def __init__(self, dry_run: bool = False, auto_apply: bool = False):
        """
        Initialize autoremediation engine.

        Args:
            dry_run: Preview actions without applying them
            auto_apply: Automatically apply high-confidence fixes
        """
        self.dry_run = dry_run
        self.auto_apply = auto_apply
        self._action_history: list[RemediationAction] = []

    def remediate_dependency_sync_failure(
        self,
        error_log: str,
        contract_path: Path = Path("configs/dependencies/contract.toml"),
    ) -> RemediationResult:
        """
        Remediate dependency sync failures.

        Common causes:
        - Outdated Poetry lock file
        - Contract/lock mismatch
        - Corrupted virtual environment
        """
        actions: list[RemediationAction] = []

        if "poetry.lock" in error_log.lower() or "out of date" in error_log.lower():
            actions.append(
                RemediationAction(
                    action_type="command",
                    description="Regenerate Poetry lock file",
                    command=["poetry", "lock", "--no-update"],
                    confidence=0.9,
                    auto_apply=True,
                    rollback_command=["git", "checkout", "poetry.lock"],
                )
            )

        if "not found" in error_log.lower() or "no module" in error_log.lower():
            actions.append(
                RemediationAction(
                    action_type="command",
                    description="Reinstall dependencies",
                    command=["poetry", "install", "--sync"],
                    confidence=0.8,
                    auto_apply=True,
                )
            )

        if "version conflict" in error_log.lower():
            actions.append(
                RemediationAction(
                    action_type="command",
                    description="Resolve version conflicts and regenerate lock",
                    command=["poetry", "update"],
                    confidence=0.7,
                    auto_apply=False,
                )
            )

        return self._apply_actions(actions)

    def remediate_wheelhouse_failure(
        self,
        failure_summary: dict[str, Any],
    ) -> RemediationResult:
        """
        Remediate wheelhouse build failures.

        Uses WheelhouseRemediator output to generate fix actions.
        """
        actions: list[RemediationAction] = []

        failures = failure_summary.get("failures", [])

        for failure in failures:
            package = failure.get("package")
            fallback = failure.get("fallback_version")

            if fallback:
                # High confidence - pin to fallback version
                actions.append(
                    RemediationAction(
                        action_type="manual",
                        description=f"Pin {package} to working version {fallback}",
                        confidence=0.85,
                        auto_apply=False,
                    )
                )
            else:
                # Lower confidence - suggest investigation
                actions.append(
                    RemediationAction(
                        action_type="manual",
                        description=f"Investigate {package} wheel availability",
                        confidence=0.5,
                        auto_apply=False,
                    )
                )

        return self._apply_actions(actions)

    def remediate_mirror_corruption(
        self,
        mirror_path: Path,
    ) -> RemediationResult:
        """
        Remediate PyPI mirror corruption.

        Checks for common issues:
        - Missing index files
        - Incomplete downloads
        - Permission problems
        """
        actions: list[RemediationAction] = []

        if not mirror_path.exists():
            actions.append(
                RemediationAction(
                    action_type="command",
                    description=f"Create mirror directory: {mirror_path}",
                    command=["mkdir", "-p", str(mirror_path)],
                    confidence=1.0,
                    auto_apply=True,
                )
            )
        else:
            # Check for index file
            index_html = mirror_path / "simple" / "index.html"
            if not index_html.exists():
                actions.append(
                    RemediationAction(
                        action_type="manual",
                        description="Mirror index missing - re-sync from source",
                        confidence=0.8,
                        auto_apply=False,
                    )
                )

        return self._apply_actions(actions)

    def remediate_artifact_validation_failure(
        self,
        validation_result: dict[str, Any],
        artifact_path: Path,
    ) -> RemediationResult:
        """
        Remediate artifact validation failures.

        Common issues:
        - Missing manifest
        - Empty wheelhouse
        - Corrupted archives
        """
        actions: list[RemediationAction] = []

        errors = validation_result.get("errors", [])

        for error in errors:
            error_str = str(error).lower()

            if "manifest" in error_str:
                actions.append(
                    RemediationAction(
                        action_type="command",
                        description="Regenerate artifact manifest",
                        command=[
                            "python",
                            "-m",
                            "chiron",
                            "package",
                            "offline",
                            "--manifest-only",
                        ],
                        confidence=0.7,
                        auto_apply=False,
                    )
                )

            if "no wheel files" in error_str:
                actions.append(
                    RemediationAction(
                        action_type="manual",
                        description="Rebuild wheelhouse - no wheels found",
                        confidence=0.9,
                        auto_apply=False,
                    )
                )

            if "corrupted" in error_str or "invalid" in error_str:
                actions.append(
                    RemediationAction(
                        action_type="command",
                        description=f"Remove corrupted artifact and re-download",
                        command=["rm", "-rf", str(artifact_path)],
                        confidence=0.6,
                        auto_apply=False,
                        rollback_command=None,  # Can't rollback deletion
                    )
                )

        return self._apply_actions(actions)

    def remediate_configuration_drift(
        self,
        drift_report: dict[str, Any],
    ) -> RemediationResult:
        """
        Remediate configuration drift between contract and lock.

        Syncs manifests when drift is detected.
        """
        actions: list[RemediationAction] = []

        drift_count = drift_report.get("drift_count", 0)

        if drift_count > 0:
            actions.append(
                RemediationAction(
                    action_type="command",
                    description=f"Sync {drift_count} drifted dependencies",
                    command=[
                        "python",
                        "-m",
                        "chiron",
                        "deps",
                        "sync",
                        "--apply",
                        "--force",
                    ],
                    confidence=0.85,
                    auto_apply=True,
                    rollback_command=[
                        "git",
                        "checkout",
                        "pyproject.toml",
                        "poetry.lock",
                    ],
                )
            )

        return self._apply_actions(actions)

    def _apply_actions(
        self,
        actions: list[RemediationAction],
    ) -> RemediationResult:
        """Apply remediation actions based on confidence and auto_apply setting."""
        applied: list[str] = []
        failed: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []

        for action in actions:
            self._action_history.append(action)

            # Determine if we should apply this action
            should_apply = (
                action.auto_apply
                and self.auto_apply
                and action.confidence >= 0.7
                and not self.dry_run
            )

            if self.dry_run:
                logger.info(f"[DRY RUN] Would apply: {action.description}")
                applied.append(action.description)
                continue

            if not should_apply:
                if action.action_type == "manual":
                    warnings.append(f"Manual action required: {action.description}")
                else:
                    warnings.append(f"Skipped (low confidence): {action.description}")
                continue

            # Apply the action
            try:
                if action.action_type == "command" and action.command:
                    logger.info(f"Applying: {action.description}")
                    result = subprocess.run(
                        action.command,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )

                    if result.returncode != 0:
                        failed.append(action.description)
                        errors.append(f"{action.description}: {result.stderr}")
                    else:
                        applied.append(action.description)
                        logger.info(f"✓ Applied: {action.description}")

                elif (
                    action.action_type == "file_edit"
                    and action.file_path
                    and action.file_content
                ):
                    logger.info(f"Applying: {action.description}")
                    action.file_path.parent.mkdir(parents=True, exist_ok=True)
                    action.file_path.write_text(action.file_content)
                    applied.append(action.description)
                    logger.info(f"✓ Applied: {action.description}")

                else:
                    warnings.append(f"Cannot auto-apply: {action.description}")

            except subprocess.TimeoutExpired:
                failed.append(action.description)
                errors.append(f"{action.description}: Timeout")
            except Exception as e:
                failed.append(action.description)
                errors.append(f"{action.description}: {e}")

        success = len(failed) == 0 and len(errors) == 0

        return RemediationResult(
            success=success,
            actions_applied=applied,
            actions_failed=failed,
            errors=errors,
            warnings=warnings,
        )

    def get_action_history(self) -> list[RemediationAction]:
        """Get history of all actions evaluated."""
        return self._action_history.copy()


def main() -> int:
    """CLI entry point for autoremediation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Intelligent autoremediation for common Chiron failures",
    )
    parser.add_argument(
        "failure_type",
        choices=["dependency-sync", "wheelhouse", "mirror", "artifact", "drift"],
        help="Type of failure to remediate",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input file (error log or JSON report)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without applying them",
    )
    parser.add_argument(
        "--auto-apply",
        action="store_true",
        help="Automatically apply high-confidence fixes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    remediator = AutoRemediator(dry_run=args.dry_run, auto_apply=args.auto_apply)

    # Load input if provided
    if args.input:
        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        if args.input.suffix == ".json":
            with args.input.open() as f:
                input_data = json.load(f)
        else:
            input_data = args.input.read_text()
    else:
        input_data = {}

    # Apply appropriate remediation
    if args.failure_type == "dependency-sync":
        if isinstance(input_data, str):
            result = remediator.remediate_dependency_sync_failure(input_data)
        else:
            logger.error("Dependency sync requires error log as input")
            return 1

    elif args.failure_type == "wheelhouse":
        if isinstance(input_data, dict):
            result = remediator.remediate_wheelhouse_failure(input_data)
        else:
            logger.error("Wheelhouse remediation requires JSON report as input")
            return 1

    elif args.failure_type == "mirror":
        mirror_path = (
            Path(input_data) if isinstance(input_data, str) else Path("vendor/mirror")
        )
        result = remediator.remediate_mirror_corruption(mirror_path)

    elif args.failure_type == "artifact":
        if isinstance(input_data, dict):
            artifact_path = Path(input_data.get("artifact_path", "dist"))
            result = remediator.remediate_artifact_validation_failure(
                input_data, artifact_path
            )
        else:
            logger.error("Artifact remediation requires validation JSON as input")
            return 1

    elif args.failure_type == "drift":
        if isinstance(input_data, dict):
            result = remediator.remediate_configuration_drift(input_data)
        else:
            logger.error("Drift remediation requires drift report JSON as input")
            return 1

    else:
        logger.error(f"Unknown failure type: {args.failure_type}")
        return 1

    # Report results
    if result.success:
        logger.info("✅ Remediation successful")
    else:
        logger.warning("⚠️  Remediation completed with issues")

    if result.actions_applied:
        logger.info("\nActions applied:")
        for action in result.actions_applied:
            logger.info(f"  ✓ {action}")

    if result.actions_failed:
        logger.error("\nActions failed:")
        for action in result.actions_failed:
            logger.error(f"  ✗ {action}")

    if result.warnings:
        logger.warning("\nWarnings:")
        for warning in result.warnings:
            logger.warning(f"  ⚠ {warning}")

    if result.errors:
        logger.error("\nErrors:")
        for error in result.errors:
            logger.error(f"  • {error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
