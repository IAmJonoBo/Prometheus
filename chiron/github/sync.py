#!/usr/bin/env python3
"""
GitHub Actions artifact synchronization and management.

This module handles downloading, validating, and syncing CI-built artifacts
(wheelhouses, packages, models) from GitHub Actions to local environments.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_TYPES = [
    "offline-packaging-suite",
    "wheelhouse-linux",
    "wheelhouse-macos",
    "wheelhouse-windows",
    "models-cache",
    "dependency-reports",
]


@dataclass
class ArtifactMetadata:
    """Metadata for a GitHub Actions artifact."""

    name: str
    size_bytes: int
    created_at: str
    workflow_run_id: int | None = None
    download_path: Path | None = None
    validated: bool = False
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    """Result of artifact synchronization operation."""

    success: bool
    artifacts_downloaded: list[str]
    artifacts_validated: list[str]
    artifacts_failed: list[str]
    target_directory: Path | None = None
    errors: list[str] = field(default_factory=list)


class GitHubArtifactSync:
    """
    Handles GitHub Actions artifact download and synchronization.

    This class provides a unified interface for:
    - Downloading artifacts from GitHub Actions workflow runs
    - Validating artifact integrity and structure
    - Syncing artifacts to local vendor/ or dist/ directories
    - Managing artifact metadata and checksums
    """

    def __init__(
        self,
        repo: str = "IAmJonoBo/Prometheus",
        target_dir: Path | None = None,
        verbose: bool = False,
    ):
        """
        Initialize GitHub artifact sync.

        Args:
            repo: GitHub repository in owner/repo format
            target_dir: Local directory for artifacts (default: vendor/artifacts)
            verbose: Enable verbose logging
        """
        self.repo = repo
        self.target_dir = target_dir or Path("vendor/artifacts")
        self.verbose = verbose
        self._gh_available = self._check_gh_cli()

    def _check_gh_cli(self) -> bool:
        """Check if GitHub CLI is available."""
        try:
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def download_artifacts(
        self,
        run_id: int | str,
        artifact_names: list[str] | None = None,
        output_dir: Path | None = None,
    ) -> SyncResult:
        """
        Download artifacts from a specific workflow run.

        Args:
            run_id: GitHub Actions workflow run ID
            artifact_names: Specific artifacts to download (None = all)
            output_dir: Override output directory

        Returns:
            SyncResult with download status and metadata
        """
        if not self._gh_available:
            return SyncResult(
                success=False,
                artifacts_downloaded=[],
                artifacts_validated=[],
                artifacts_failed=[],
                errors=[
                    "GitHub CLI (gh) not available. Install from https://cli.github.com/"
                ],
            )

        output_dir = output_dir or self.target_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[str] = []
        failed: list[str] = []
        errors: list[str] = []

        # Use artifact_names or default types
        targets = artifact_names or DEFAULT_ARTIFACT_TYPES

        for artifact_name in targets:
            try:
                logger.info(f"Downloading artifact: {artifact_name} from run {run_id}")

                cmd = [
                    "gh",
                    "run",
                    "download",
                    str(run_id),
                    "-n",
                    artifact_name,
                    "-D",
                    str(output_dir / artifact_name),
                    "-R",
                    self.repo,
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout per artifact
                )

                if result.returncode == 0:
                    downloaded.append(artifact_name)
                    logger.info(f"✓ Downloaded: {artifact_name}")
                else:
                    failed.append(artifact_name)
                    error_msg = result.stderr.strip() or "Unknown error"
                    errors.append(f"{artifact_name}: {error_msg}")
                    logger.warning(f"✗ Failed: {artifact_name} - {error_msg}")

            except subprocess.TimeoutExpired:
                failed.append(artifact_name)
                errors.append(f"{artifact_name}: Download timeout (>5 minutes)")
                logger.error(f"✗ Timeout: {artifact_name}")
            except Exception as e:
                failed.append(artifact_name)
                errors.append(f"{artifact_name}: {e!s}")
                logger.error(f"✗ Error: {artifact_name} - {e}")

        return SyncResult(
            success=len(downloaded) > 0 and len(failed) == 0,
            artifacts_downloaded=downloaded,
            artifacts_validated=[],
            artifacts_failed=failed,
            target_directory=output_dir,
            errors=errors,
        )

    def validate_artifacts(
        self,
        artifact_dir: Path,
        artifact_type: Literal[
            "wheelhouse", "offline-package", "models"
        ] = "wheelhouse",
    ) -> dict[str, Any]:
        """
        Validate artifact structure and integrity.

        Args:
            artifact_dir: Directory containing artifacts
            artifact_type: Type of artifact to validate

        Returns:
            Validation results with status and details
        """
        if not artifact_dir.exists():
            return {
                "valid": False,
                "errors": [f"Artifact directory not found: {artifact_dir}"],
            }

        validation: dict[str, Any] = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "metadata": {},
        }

        if artifact_type == "wheelhouse":
            # Check for wheelhouse structure
            manifest_path = artifact_dir / "manifest.json"
            if not manifest_path.exists():
                validation["warnings"].append("manifest.json not found")
            else:
                try:
                    with manifest_path.open() as f:
                        manifest = json.load(f)
                    validation["metadata"]["wheel_count"] = manifest.get(
                        "wheel_count", 0
                    )
                except Exception as e:
                    validation["errors"].append(f"Failed to parse manifest: {e}")
                    validation["valid"] = False

            # Count actual wheel files
            wheel_files = list(artifact_dir.glob("**/*.whl"))
            validation["metadata"]["wheels_found"] = len(wheel_files)

            if len(wheel_files) == 0:
                validation["errors"].append("No wheel files found")
                validation["valid"] = False

        elif artifact_type == "offline-package":
            # Check for complete offline package structure
            required_dirs = ["wheelhouse", "models", "containers"]
            for dir_name in required_dirs:
                dir_path = artifact_dir / dir_name
                if not dir_path.exists():
                    validation["warnings"].append(f"Missing {dir_name}/ directory")

        elif artifact_type == "models":
            # Check for model files
            model_files = list(artifact_dir.glob("**/*.bin")) + list(
                artifact_dir.glob("**/*.safetensors")
            )
            validation["metadata"]["model_files_found"] = len(model_files)

            if len(model_files) == 0:
                validation["warnings"].append("No model files found")

        return validation

    def sync_to_local(
        self,
        artifact_dir: Path,
        target: Literal["vendor", "dist", "var"] = "vendor",
        merge: bool = False,
    ) -> bool:
        """
        Sync downloaded artifacts to local project directories.

        Args:
            artifact_dir: Source artifact directory
            target: Target location (vendor/, dist/, or var/)
            merge: Merge with existing content vs. replace

        Returns:
            True if sync successful
        """
        target_map = {
            "vendor": Path("vendor"),
            "dist": Path("dist"),
            "var": Path("var/artifacts"),
        }

        target_path = target_map.get(target)
        if not target_path:
            logger.error(f"Invalid target: {target}")
            return False

        target_path.mkdir(parents=True, exist_ok=True)

        try:
            if not merge and target_path.exists():
                # Clear existing content
                for item in target_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

            # Copy artifacts
            if artifact_dir.is_dir():
                for item in artifact_dir.iterdir():
                    dest = target_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=merge)
                    else:
                        shutil.copy2(item, dest)

            logger.info(f"✓ Synced artifacts to {target_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to sync artifacts: {e}")
            return False


def download_artifacts(
    run_id: int | str,
    artifact_names: list[str] | None = None,
    output_dir: Path | None = None,
    repo: str = "IAmJonoBo/Prometheus",
) -> SyncResult:
    """
    Convenience function to download artifacts from a workflow run.

    Args:
        run_id: GitHub Actions workflow run ID
        artifact_names: Specific artifacts to download (None = all defaults)
        output_dir: Output directory (default: vendor/artifacts)
        repo: GitHub repository in owner/repo format

    Returns:
        SyncResult with download status
    """
    syncer = GitHubArtifactSync(repo=repo, target_dir=output_dir)
    return syncer.download_artifacts(run_id, artifact_names, output_dir)


def validate_artifacts(
    artifact_dir: Path,
    artifact_type: Literal["wheelhouse", "offline-package", "models"] = "wheelhouse",
) -> dict[str, Any]:
    """
    Convenience function to validate artifacts.

    Args:
        artifact_dir: Directory containing artifacts
        artifact_type: Type of artifact to validate

    Returns:
        Validation results dictionary
    """
    syncer = GitHubArtifactSync()
    return syncer.validate_artifacts(artifact_dir, artifact_type)


def sync_to_local(
    artifact_dir: Path,
    target: Literal["vendor", "dist", "var"] = "vendor",
    merge: bool = False,
) -> bool:
    """
    Convenience function to sync artifacts to local directories.

    Args:
        artifact_dir: Source artifact directory
        target: Target location (vendor/, dist/, or var/)
        merge: Merge with existing content vs. replace

    Returns:
        True if sync successful
    """
    syncer = GitHubArtifactSync()
    return syncer.sync_to_local(artifact_dir, target, merge)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for GitHub artifact sync."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync GitHub Actions artifacts to local environment",
    )
    parser.add_argument(
        "run_id",
        type=str,
        help="GitHub Actions workflow run ID",
    )
    parser.add_argument(
        "--artifacts",
        nargs="+",
        help="Specific artifacts to download (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("vendor/artifacts"),
        help="Output directory for artifacts",
    )
    parser.add_argument(
        "--repo",
        default="IAmJonoBo/Prometheus",
        help="GitHub repository (owner/repo)",
    )
    parser.add_argument(
        "--sync-to",
        choices=["vendor", "dist", "var"],
        help="Sync artifacts to specified location after download",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge with existing content (default: replace)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate artifacts after download",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Download artifacts
    syncer = GitHubArtifactSync(
        repo=args.repo,
        target_dir=args.output_dir,
        verbose=args.verbose,
    )

    result = syncer.download_artifacts(
        args.run_id,
        args.artifacts,
        args.output_dir,
    )

    if not result.success:
        logger.error("❌ Artifact download failed:")
        for error in result.errors:
            logger.error(f"  - {error}")
        return 1

    logger.info(f"✅ Downloaded {len(result.artifacts_downloaded)} artifacts")

    # Validate if requested
    if args.validate:
        for artifact_name in result.artifacts_downloaded:
            artifact_path = args.output_dir / artifact_name
            validation = syncer.validate_artifacts(artifact_path, "wheelhouse")

            if validation["valid"]:
                logger.info(f"✅ {artifact_name}: Valid")
            else:
                logger.warning(f"⚠️  {artifact_name}: Validation issues")
                for error in validation["errors"]:
                    logger.warning(f"    - {error}")

    # Sync if requested
    if args.sync_to:
        for artifact_name in result.artifacts_downloaded:
            artifact_path = args.output_dir / artifact_name
            success = syncer.sync_to_local(artifact_path, args.sync_to, args.merge)

            if not success:
                logger.error(f"Failed to sync {artifact_name}")
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
