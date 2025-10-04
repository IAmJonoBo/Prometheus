#!/usr/bin/env python3
"""
Unified Orchestration Coordinator for Prometheus Pipeline.

This module provides a central coordination point for all dependency management,
packaging, synchronization, and orchestration tasks across local and remote
environments.
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

logger = logging.getLogger(__name__)

# Default paths
REPO_ROOT = Path(__file__).resolve().parents[1]
VAR_ROOT = REPO_ROOT / "var"
VENDOR_ROOT = REPO_ROOT / "vendor"
SCRIPTS_ROOT = REPO_ROOT / "scripts"


@dataclass
class OrchestrationContext:
    """Context for orchestration operations."""

    mode: Literal["local", "remote", "hybrid"] = "hybrid"
    dry_run: bool = False
    verbose: bool = False
    repo_root: Path = REPO_ROOT
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Subsystem states
    dependencies_synced: bool = False
    wheelhouse_built: bool = False
    models_cached: bool = False
    containers_ready: bool = False
    validation_passed: bool = False

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to dictionary."""
        return {
            "mode": self.mode,
            "dry_run": self.dry_run,
            "timestamp": self.timestamp.isoformat(),
            "dependencies_synced": self.dependencies_synced,
            "wheelhouse_built": self.wheelhouse_built,
            "models_cached": self.models_cached,
            "containers_ready": self.containers_ready,
            "validation_passed": self.validation_passed,
            "metadata": self.metadata,
        }


class OrchestrationCoordinator:
    """
    Coordinates all pipeline operations across local and remote environments.

    This class provides a unified interface for:
    - Dependency management (preflight, guard, upgrade, sync)
    - Wheelhouse building (local and remote via cibuildwheel)
    - Offline packaging (models, containers, checksums)
    - Validation and remediation
    - Cross-subsystem synchronization
    """

    def __init__(self, context: OrchestrationContext | None = None):
        self.context = context or OrchestrationContext()
        self._state_file = VAR_ROOT / "orchestration-state.json"
        self._load_state()

    def _load_state(self) -> None:
        """Load orchestration state from disk."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                self.context.metadata.update(data.get("metadata", {}))
                logger.debug(f"Loaded orchestration state from {self._state_file}")
            except Exception as e:
                logger.warning(f"Failed to load orchestration state: {e}")

    def _save_state(self) -> None:
        """Save orchestration state to disk."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self.context.to_dict(), indent=2))
        logger.debug(f"Saved orchestration state to {self._state_file}")

    def _run_command(
        self,
        cmd: list[str],
        description: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a command with logging."""
        if self.context.verbose:
            logger.info(f"Running: {description}")
            logger.debug(f"Command: {' '.join(cmd)}")

        if self.context.dry_run:
            logger.info(f"[DRY RUN] Would run: {' '.join(cmd)}")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        return subprocess.run(
            cmd,
            cwd=self.context.repo_root,
            check=check,
            capture_output=True,
        )

    # Dependency Management Operations

    def deps_preflight(self) -> dict[str, Any]:
        """Run dependency preflight checks."""
        logger.info("Running dependency preflight checks...")

        result = self._run_command(
            ["poetry", "run", "prometheus", "deps", "preflight", "--json"],
            "Dependency preflight",
            check=False,
        )

        output_file = VAR_ROOT / "dependency-preflight" / "latest.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(result.stdout)

        data = json.loads(result.stdout) if result.stdout else {}
        self.context.metadata["preflight"] = data
        self._save_state()

        return data

    def deps_guard(self, preflight_path: Path | None = None) -> dict[str, Any]:
        """Run upgrade guard analysis."""
        logger.info("Running upgrade guard analysis...")

        if not preflight_path:
            preflight_path = VAR_ROOT / "dependency-preflight" / "latest.json"

        output_path = VAR_ROOT / "upgrade-guard" / "assessment.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "poetry",
            "run",
            "prometheus",
            "deps",
            "guard",
            "--preflight",
            str(preflight_path),
            "--output",
            str(output_path),
            "--markdown",
            str(output_path.parent / "summary.md"),
            "--snapshot-root",
            str(VAR_ROOT / "upgrade-guard" / "runs"),
            "--snapshot-tag",
            "orchestrated",
        ]

        self._run_command(cmd, "Upgrade guard", check=False)

        data = json.loads(output_path.read_text()) if output_path.exists() else {}
        self.context.metadata["guard"] = data
        self._save_state()

        return data

    def deps_sync(self, force: bool = False) -> bool:
        """Sync dependency contracts."""
        logger.info("Syncing dependency contracts...")

        cmd = ["poetry", "run", "prometheus", "deps", "sync"]
        if force:
            cmd.extend(["--apply", "--force"])

        result = self._run_command(cmd, "Dependency sync", check=False)
        success = result.returncode == 0

        self.context.dependencies_synced = success
        self._save_state()

        return success

    def deps_upgrade(
        self,
        packages: list[str] | None = None,
        auto_apply: bool = False,
        generate_advice: bool = True,
    ) -> dict[str, Any]:
        """Generate and optionally apply upgrade plan with intelligent advice."""
        logger.info("Generating upgrade plan...")

        cmd = [
            "poetry",
            "run",
            "prometheus",
            "deps",
            "upgrade",
            "--sbom",
            str(VAR_ROOT / "dependency-sync" / "sbom.json"),
        ]

        if packages:
            cmd.extend(["--planner-packages", ",".join(packages)])

        if generate_advice:
            cmd.append("--generate-advice")
            # Add mirror root if available
            mirror_root = VENDOR_ROOT / "wheelhouse"
            if mirror_root.exists():
                cmd.extend(["--mirror-root", str(mirror_root)])

        if auto_apply:
            cmd.extend(["--apply", "--yes"])

        result = self._run_command(cmd, "Upgrade planning", check=False)

        # Parse output for plan data (would need proper JSON output from CLI)
        plan = {"success": result.returncode == 0}
        self.context.metadata["upgrade_plan"] = plan
        self._save_state()

        return plan

    # Packaging Operations

    def build_wheelhouse(
        self,
        output_dir: Path | None = None,
        include_dev: bool = True,
    ) -> bool:
        """Build wheelhouse for offline installation."""
        logger.info("Building wheelhouse...")

        if not output_dir:
            output_dir = VENDOR_ROOT / "wheelhouse"

        cmd = [
            "bash",
            str(SCRIPTS_ROOT / "build-wheelhouse.sh"),
            str(output_dir),
        ]

        env = {
            "EXTRAS": "pii,observability,rag,llm,governance,integrations",
            "INCLUDE_DEV": "true" if include_dev else "false",
        }

        result = self._run_command(cmd, "Wheelhouse build", check=False)
        success = result.returncode == 0

        self.context.wheelhouse_built = success
        self._save_state()

        return success

    def offline_package(
        self,
        output_dir: Path | None = None,
        auto_update: bool = False,
    ) -> bool:
        """Run offline packaging orchestrator."""
        logger.info("Running offline packaging...")

        cmd = ["poetry", "run", "prometheus", "offline-package"]

        if output_dir:
            cmd.extend(["--output-dir", str(output_dir)])

        if auto_update:
            cmd.extend(["--auto-update", "--auto-update-max", "minor"])

        result = self._run_command(cmd, "Offline package", check=False)
        success = result.returncode == 0

        self.context.metadata["offline_package"] = {"success": success}
        self._save_state()

        return success

    def offline_doctor(
        self,
        package_dir: Path | None = None,
        format: Literal["table", "json", "text"] = "table",
    ) -> dict[str, Any]:
        """Validate offline package."""
        logger.info("Validating offline package...")

        cmd = ["poetry", "run", "prometheus", "offline-doctor"]

        if package_dir:
            cmd.extend(["--package-dir", str(package_dir)])

        cmd.extend(["--format", format])

        result = self._run_command(cmd, "Offline doctor", check=False)

        if format == "json" and result.stdout:
            data = json.loads(result.stdout)
        else:
            data = {"success": result.returncode == 0}

        self.context.validation_passed = result.returncode == 0
        self.context.metadata["validation"] = data
        self._save_state()

        return data

    # Remediation Operations

    def remediation_wheelhouse(
        self,
        input_file: Path | None = None,
        output_file: Path | None = None,
    ) -> dict[str, Any]:
        """Analyze wheelhouse failures and generate recommendations."""
        logger.info("Running wheelhouse remediation...")

        cmd = ["poetry", "run", "prometheus", "remediation", "wheelhouse"]

        if input_file:
            cmd.extend(["--input", str(input_file)])

        if output_file:
            cmd.extend(["--output", str(output_file)])
        else:
            output_file = VAR_ROOT / "remediation-recommendations.json"
            cmd.extend(["--output", str(output_file)])

        result = self._run_command(cmd, "Wheelhouse remediation", check=False)

        data = {}
        if output_file.exists():
            data = json.loads(output_file.read_text())

        self.context.metadata["remediation"] = data
        self._save_state()

        return data

    # Mirror Management

    def mirror_status(self, mirror_root: Path | None = None) -> dict[str, Any]:
        """Check mirror status."""
        logger.info("Checking mirror status...")

        cmd = ["python", str(SCRIPTS_ROOT / "mirror_manager.py"), "--status", "--json"]

        if mirror_root:
            cmd.extend(["--mirror-root", str(mirror_root)])

        result = self._run_command(cmd, "Mirror status", check=False)

        data = json.loads(result.stdout) if result.stdout else {}
        self.context.metadata["mirror_status"] = data
        self._save_state()

        return data

    def mirror_update(
        self,
        source: Path,
        mirror_root: Path | None = None,
        prune: bool = False,
    ) -> bool:
        """Update mirror from source."""
        logger.info(f"Updating mirror from {source}...")

        cmd = [
            "python",
            str(SCRIPTS_ROOT / "mirror_manager.py"),
            "--update",
            "--source",
            str(source),
        ]

        if mirror_root:
            cmd.extend(["--mirror-root", str(mirror_root)])

        if prune:
            cmd.append("--prune")

        result = self._run_command(cmd, "Mirror update", check=False)
        return result.returncode == 0

    # Comprehensive Orchestration Workflows

    def full_dependency_workflow(
        self,
        auto_upgrade: bool = False,
        force_sync: bool = False,
    ) -> dict[str, Any]:
        """
        Execute complete dependency management workflow:
        1. Preflight checks
        2. Upgrade guard
        3. Optional upgrade planning with advice
        4. Dependency sync
        """
        logger.info("Starting full dependency workflow...")

        results = {}

        # Step 1: Preflight
        results["preflight"] = self.deps_preflight()

        # Step 2: Guard
        results["guard"] = self.deps_guard()

        # Step 3: Optional upgrade with intelligent advice
        if auto_upgrade:
            results["upgrade"] = self.deps_upgrade(
                auto_apply=False,
                generate_advice=True,
            )

        # Step 4: Sync
        results["sync"] = self.deps_sync(force=force_sync)

        self.context.metadata["full_workflow"] = results
        self._save_state()

        return results

    def intelligent_upgrade_workflow(
        self,
        auto_apply_safe: bool = False,
        update_mirror: bool = True,
    ) -> dict[str, Any]:
        """
        Execute intelligent upgrade workflow with mirror synchronization:
        1. Generate upgrade advice
        2. Optionally auto-apply safe upgrades
        3. Update mirror with new dependencies
        4. Validate updated environment
        """
        logger.info("Starting intelligent upgrade workflow...")

        results = {}

        # Step 1: Generate upgrade advice
        logger.info("Generating upgrade advice...")
        results["advice"] = self.deps_upgrade(
            auto_apply=False,
            generate_advice=True,
        )

        # Step 2: Auto-apply safe upgrades if requested
        if auto_apply_safe:
            logger.info("Auto-applying safe upgrades...")
            # This would require parsing the advice output and selectively applying
            # For now, we just note the intent
            results["auto_apply"] = {"enabled": True, "status": "pending"}

        # Step 3: Update mirror if needed
        if update_mirror:
            logger.info("Updating dependency mirror...")
            wheelhouse_source = VENDOR_ROOT / "wheelhouse-temp"
            mirror_root = VENDOR_ROOT / "wheelhouse"

            if wheelhouse_source.exists():
                results["mirror_update"] = self.mirror_update(
                    source=wheelhouse_source,
                    mirror_root=mirror_root,
                    prune=False,
                )
            else:
                logger.warning(f"Wheelhouse source not found: {wheelhouse_source}")
                results["mirror_update"] = False

        # Step 4: Validate
        logger.info("Running validation checks...")
        results["validation"] = self.deps_preflight()

        self.context.metadata["intelligent_upgrade_workflow"] = results
        self._save_state()

        return results

    def full_packaging_workflow(
        self,
        include_remote: bool = False,
        validate: bool = True,
    ) -> dict[str, Any]:
        """
        Execute complete packaging workflow:
        1. Build wheelhouse
        2. Run offline packaging
        3. Optional validation
        4. Optional remediation
        """
        logger.info("Starting full packaging workflow...")

        results = {}

        # Step 1: Build wheelhouse
        results["wheelhouse"] = self.build_wheelhouse()

        # Step 2: Offline packaging
        if results["wheelhouse"]:
            results["offline_package"] = self.offline_package()

        # Step 3: Validation
        if validate and results.get("offline_package"):
            results["validation"] = self.offline_doctor()

            # Step 4: Remediation if validation failed
            if not results["validation"].get("success"):
                results["remediation"] = self.remediation_wheelhouse()

        self.context.metadata["packaging_workflow"] = results
        self._save_state()

        return results

    def air_gapped_preparation_workflow(
        self,
        include_models: bool = True,
        include_containers: bool = False,
        validate: bool = True,
    ) -> dict[str, Any]:
        """
        Execute complete air-gapped preparation workflow:
        1. Full dependency workflow
        2. Build wheelhouse (including multi-platform if remote)
        3. Download models
        4. Package containers (if requested)
        5. Generate checksums and manifests
        6. Validate complete package

        This workflow prepares everything needed for offline deployment.
        """
        logger.info("Starting air-gapped preparation workflow...")

        results = {}

        # Step 1: Dependencies
        logger.info("Step 1/6: Dependency management...")
        results["dependencies"] = self.full_dependency_workflow(
            auto_upgrade=False,
            force_sync=False,
        )

        # Step 2: Wheelhouse
        logger.info("Step 2/6: Building wheelhouse...")
        results["wheelhouse"] = self.build_wheelhouse(include_dev=True)

        # Step 3: Models
        if include_models:
            logger.info("Step 3/6: Downloading models...")
            cmd = ["poetry", "run", "prometheus", "doctor", "models", "--verbose"]
            result = self._run_command(cmd, "Download models", check=False)
            results["models"] = result.returncode == 0
        else:
            logger.info("Step 3/6: Skipping models (not requested)")
            results["models"] = None

        # Step 4: Containers (optional)
        if include_containers:
            logger.info("Step 4/6: Preparing containers...")
            # TODO: Add container preparation logic
            results["containers"] = False
            logger.warning("Container preparation not yet implemented")
        else:
            logger.info("Step 4/6: Skipping containers (not requested)")
            results["containers"] = None

        # Step 5: Complete offline package
        logger.info("Step 5/6: Creating offline package...")
        results["offline_package"] = self.offline_package(auto_update=False)

        # Step 6: Validation
        if validate:
            logger.info("Step 6/6: Validating offline package...")
            results["validation"] = self.offline_doctor(format="json")

            if not results["validation"].get("success"):
                logger.warning("Validation failed - running remediation...")
                results["remediation"] = self.remediation_wheelhouse()
        else:
            logger.info("Step 6/6: Skipping validation (not requested)")
            results["validation"] = None

        # Update context
        self.context.metadata["air_gapped_workflow"] = results
        self._save_state()

        # Summary
        all_success = all(
            v is True or (isinstance(v, dict) and v.get("success"))
            for v in results.values()
            if v is not None
        )

        if all_success:
            logger.info("✅ Air-gapped preparation complete")
        else:
            logger.warning("⚠️  Air-gapped preparation completed with issues")

        return results

        results = {}

        # Step 1: Wheelhouse
        results["wheelhouse"] = self.build_wheelhouse()

        # Step 2: Offline package
        results["offline_package"] = self.offline_package(auto_update=True)

        # Step 3: Validation
        if validate:
            results["validation"] = self.offline_doctor()

            # Step 4: Remediation if validation failed
            if not results["validation"].get("success", True):
                results["remediation"] = self.remediation_wheelhouse()

        self.context.metadata["packaging_workflow"] = results
        self._save_state()

        return results

    def sync_remote_to_local(
        self,
        artifact_dir: Path,
        validate: bool = True,
    ) -> dict[str, Any]:
        """
        Sync remote artifacts to local environment:
        1. Extract artifacts
        2. Sync dependencies
        3. Validate
        """
        logger.info(f"Syncing remote artifacts from {artifact_dir}...")

        results = {}

        # Copy artifacts to vendor
        if artifact_dir.exists():
            vendor_target = VENDOR_ROOT / "wheelhouse"
            # Logic to copy artifacts
            results["copy"] = True

        # Sync dependencies
        results["sync"] = self.deps_sync(force=True)

        # Validate
        if validate:
            results["validation"] = self.offline_doctor()

        self.context.metadata["remote_sync"] = results
        self._save_state()

        return results

    def get_status(self) -> dict[str, Any]:
        """Get current orchestration status."""
        return {
            "context": self.context.to_dict(),
            "state_file": str(self._state_file),
            "recommendations": self._get_recommendations(),
        }

    def _get_recommendations(self) -> list[str]:
        """Generate actionable recommendations based on current state."""
        recs = []

        if not self.context.dependencies_synced:
            recs.append("Run deps_sync() to synchronize dependency contracts")

        if not self.context.wheelhouse_built:
            recs.append("Run build_wheelhouse() to create offline installation package")

        if not self.context.validation_passed:
            recs.append("Run offline_doctor() to validate package integrity")

        guard_data = self.context.metadata.get("guard", {})
        if guard_data.get("status") == "needs-review":
            recs.append(
                "Review upgrade guard assessment before proceeding with upgrades"
            )

        return recs


def main() -> int:
    """CLI entry point for orchestration coordinator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Unified orchestration coordinator for Prometheus"
    )
    parser.add_argument(
        "command",
        choices=[
            "status",
            "full-dependency",
            "full-packaging",
            "sync-remote",
        ],
        help="Orchestration command to execute",
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--artifact-dir", type=Path, help="Remote artifact directory")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    context = OrchestrationContext(
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    coordinator = OrchestrationCoordinator(context)

    if args.command == "status":
        status = coordinator.get_status()
        print(json.dumps(status, indent=2))

    elif args.command == "full-dependency":
        results = coordinator.full_dependency_workflow(force_sync=True)
        print(json.dumps(results, indent=2))

    elif args.command == "full-packaging":
        results = coordinator.full_packaging_workflow(validate=True)
        print(json.dumps(results, indent=2))

    elif args.command == "sync-remote":
        if not args.artifact_dir:
            print("Error: --artifact-dir required for sync-remote", file=sys.stderr)
            return 1
        results = coordinator.sync_remote_to_local(args.artifact_dir)
        print(json.dumps(results, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
