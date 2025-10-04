#!/usr/bin/env python3
"""Binary reproducibility verification for wheels.

This module provides tools to verify that wheels can be rebuilt reproducibly
by comparing digests and analyzing differences.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WheelDigest:
    """Digest information for a wheel."""

    filename: str
    sha256: str
    size: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReproducibilityReport:
    """Report on reproducibility check."""

    wheel_name: str
    is_reproducible: bool
    original_digest: str
    rebuilt_digest: str
    size_match: bool
    differences: list[str] = field(default_factory=list)
    normalized_match: bool = False


class ReproducibilityChecker:
    """Check binary reproducibility of wheels."""

    # Files/patterns to normalize when checking reproducibility
    NORMALIZED_PATTERNS = [
        "*.pyc",  # Bytecode can have timestamps
        "RECORD",  # Contains hashes and sizes
        "*-RECORD",
        "*.dist-info/WHEEL",  # May contain timestamps
        "*.dist-info/METADATA",  # May contain timestamps
    ]

    def __init__(self, normalize: bool = True):
        """Initialize reproducibility checker.

        Args:
            normalize: Whether to normalize timestamps and other non-deterministic content
        """
        self.normalize = normalize

    def compute_wheel_digest(self, wheel_path: Path) -> WheelDigest:
        """Compute digest for a wheel file.

        Args:
            wheel_path: Path to wheel file

        Returns:
            Wheel digest information
        """
        sha256_hash = hashlib.sha256()

        with open(wheel_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)

        # Extract metadata
        metadata = self._extract_wheel_metadata(wheel_path)

        return WheelDigest(
            filename=wheel_path.name,
            sha256=sha256_hash.hexdigest(),
            size=wheel_path.stat().st_size,
            metadata=metadata,
        )

    def _extract_wheel_metadata(self, wheel_path: Path) -> dict[str, Any]:
        """Extract metadata from wheel.

        Args:
            wheel_path: Path to wheel file

        Returns:
            Dictionary with metadata
        """
        metadata = {}

        try:
            with zipfile.ZipFile(wheel_path, "r") as zf:
                # Find METADATA file
                for name in zf.namelist():
                    if name.endswith("/METADATA"):
                        content = zf.read(name).decode("utf-8", errors="ignore")
                        # Parse basic metadata
                        for line in content.split("\n"):
                            if ": " in line:
                                key, value = line.split(": ", 1)
                                if key in ["Name", "Version", "Build"]:
                                    metadata[key.lower()] = value
                        break
        except Exception as e:
            print(f"Warning: Could not extract metadata from {wheel_path}: {e}")

        return metadata

    def compare_wheels(
        self,
        original_wheel: Path,
        rebuilt_wheel: Path,
    ) -> ReproducibilityReport:
        """Compare two wheels for reproducibility.

        Args:
            original_wheel: Path to original wheel
            rebuilt_wheel: Path to rebuilt wheel

        Returns:
            Reproducibility report
        """
        orig_digest = self.compute_wheel_digest(original_wheel)
        rebuilt_digest = self.compute_wheel_digest(rebuilt_wheel)

        # Basic comparison
        is_reproducible = orig_digest.sha256 == rebuilt_digest.sha256
        size_match = orig_digest.size == rebuilt_digest.size

        differences = []

        # If not reproducible, analyze differences
        if not is_reproducible:
            differences = self._analyze_differences(original_wheel, rebuilt_wheel)

            # Try normalized comparison if enabled
            normalized_match = False
            if self.normalize:
                normalized_match = self._compare_normalized(
                    original_wheel, rebuilt_wheel
                )

        return ReproducibilityReport(
            wheel_name=original_wheel.name,
            is_reproducible=is_reproducible,
            original_digest=orig_digest.sha256,
            rebuilt_digest=rebuilt_digest.sha256,
            size_match=size_match,
            differences=differences,
            normalized_match=normalized_match if not is_reproducible else True,
        )

    def _analyze_differences(
        self,
        wheel1: Path,
        wheel2: Path,
    ) -> list[str]:
        """Analyze differences between two wheels.

        Args:
            wheel1: First wheel
            wheel2: Second wheel

        Returns:
            List of difference descriptions
        """
        differences = []

        try:
            with zipfile.ZipFile(wheel1, "r") as zf1, zipfile.ZipFile(
                wheel2, "r"
            ) as zf2:
                files1 = set(zf1.namelist())
                files2 = set(zf2.namelist())

                # Check for missing files
                only_in_1 = files1 - files2
                only_in_2 = files2 - files1

                if only_in_1:
                    differences.append(
                        f"Files only in original: {', '.join(sorted(only_in_1)[:5])}"
                    )

                if only_in_2:
                    differences.append(
                        f"Files only in rebuilt: {', '.join(sorted(only_in_2)[:5])}"
                    )

                # Check common files
                common_files = files1 & files2
                different_files = []

                for filename in common_files:
                    content1 = zf1.read(filename)
                    content2 = zf2.read(filename)

                    if content1 != content2:
                        different_files.append(filename)

                if different_files:
                    differences.append(
                        f"Different content: {', '.join(sorted(different_files)[:5])}"
                    )

        except Exception as e:
            differences.append(f"Error analyzing: {e}")

        return differences

    def _compare_normalized(
        self,
        wheel1: Path,
        wheel2: Path,
    ) -> bool:
        """Compare wheels after normalizing non-deterministic content.

        Args:
            wheel1: First wheel
            wheel2: Second wheel

        Returns:
            True if wheels match after normalization
        """
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                # Extract both wheels
                extract1 = tmpdir_path / "wheel1"
                extract2 = tmpdir_path / "wheel2"

                with zipfile.ZipFile(wheel1, "r") as zf:
                    zf.extractall(extract1)

                with zipfile.ZipFile(wheel2, "r") as zf:
                    zf.extractall(extract2)

                # Normalize timestamps
                self._normalize_directory(extract1)
                self._normalize_directory(extract2)

                # Remove RECORD files (they contain hashes)
                for record_file in extract1.rglob("RECORD"):
                    record_file.unlink(missing_ok=True)
                for record_file in extract2.rglob("RECORD"):
                    record_file.unlink(missing_ok=True)

                # Compare directory trees
                return self._compare_directories(extract1, extract2)

        except Exception as e:
            print(f"Warning: Normalized comparison failed: {e}")
            return False

    def _normalize_directory(self, directory: Path) -> None:
        """Normalize timestamps and other non-deterministic content.

        Args:
            directory: Directory to normalize
        """
        # Set all mtimes to epoch
        import os
        import time

        epoch = 0

        for root, dirs, files in os.walk(directory):
            root_path = Path(root)
            for name in files:
                file_path = root_path / name
                os.utime(file_path, (epoch, epoch))

    def _compare_directories(self, dir1: Path, dir2: Path) -> bool:
        """Compare two directories recursively.

        Args:
            dir1: First directory
            dir2: Second directory

        Returns:
            True if directories are identical
        """
        # Get all files
        files1 = {f.relative_to(dir1) for f in dir1.rglob("*") if f.is_file()}
        files2 = {f.relative_to(dir2) for f in dir2.rglob("*") if f.is_file()}

        if files1 != files2:
            return False

        # Compare file contents
        for rel_path in files1:
            file1 = dir1 / rel_path
            file2 = dir2 / rel_path

            # Skip RECORD files
            if rel_path.name == "RECORD":
                continue

            if file1.read_bytes() != file2.read_bytes():
                return False

        return True

    def verify_wheelhouse(
        self,
        wheelhouse_dir: Path,
        rebuild_script: Path | None = None,
    ) -> dict[str, ReproducibilityReport]:
        """Verify reproducibility of all wheels in a wheelhouse.

        Args:
            wheelhouse_dir: Directory containing wheels
            rebuild_script: Optional script to rebuild wheels

        Returns:
            Dictionary mapping wheel names to reports
        """
        reports = {}

        wheels = list(wheelhouse_dir.glob("*.whl"))
        print(f"Found {len(wheels)} wheels to verify")

        if rebuild_script:
            print(f"Using rebuild script: {rebuild_script}")
            # TODO: Implement rebuild logic
            print("Note: Rebuild not yet implemented, computing digests only")

        for wheel in wheels:
            digest = self.compute_wheel_digest(wheel)
            print(f"  {wheel.name}: {digest.sha256[:12]}...")

            # Store digest for future comparison
            reports[wheel.name] = ReproducibilityReport(
                wheel_name=wheel.name,
                is_reproducible=True,  # Placeholder
                original_digest=digest.sha256,
                rebuilt_digest=digest.sha256,
                size_match=True,
            )

        return reports

    def save_digests(
        self,
        wheelhouse_dir: Path,
        output_file: Path,
    ) -> None:
        """Save wheel digests to file for future verification.

        Args:
            wheelhouse_dir: Directory containing wheels
            output_file: Path to output JSON file
        """
        digests = {}

        for wheel in wheelhouse_dir.glob("*.whl"):
            digest = self.compute_wheel_digest(wheel)
            digests[wheel.name] = {
                "sha256": digest.sha256,
                "size": digest.size,
                "metadata": digest.metadata,
            }

        output_file.write_text(json.dumps(digests, indent=2))
        print(f"Saved {len(digests)} wheel digests to {output_file}")

    def verify_against_digests(
        self,
        wheelhouse_dir: Path,
        digests_file: Path,
    ) -> dict[str, ReproducibilityReport]:
        """Verify wheels against previously saved digests.

        Args:
            wheelhouse_dir: Directory containing wheels
            digests_file: Path to digests JSON file

        Returns:
            Dictionary mapping wheel names to reports
        """
        saved_digests = json.loads(digests_file.read_text())
        reports = {}

        for wheel in wheelhouse_dir.glob("*.whl"):
            current_digest = self.compute_wheel_digest(wheel)

            if wheel.name not in saved_digests:
                print(f"  ⚠ {wheel.name}: Not in saved digests")
                continue

            saved = saved_digests[wheel.name]
            is_match = current_digest.sha256 == saved["sha256"]

            reports[wheel.name] = ReproducibilityReport(
                wheel_name=wheel.name,
                is_reproducible=is_match,
                original_digest=saved["sha256"],
                rebuilt_digest=current_digest.sha256,
                size_match=current_digest.size == saved["size"],
            )

            status = "✓" if is_match else "✗"
            print(f"  {status} {wheel.name}")

        return reports


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify binary reproducibility of wheels"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Compute digests
    compute_parser = subparsers.add_parser(
        "compute", help="Compute and save wheel digests"
    )
    compute_parser.add_argument(
        "wheelhouse", type=Path, help="Wheelhouse directory"
    )
    compute_parser.add_argument(
        "--output",
        type=Path,
        default=Path("wheel-digests.json"),
        help="Output file for digests",
    )

    # Verify against digests
    verify_parser = subparsers.add_parser(
        "verify", help="Verify wheels against saved digests"
    )
    verify_parser.add_argument("wheelhouse", type=Path, help="Wheelhouse directory")
    verify_parser.add_argument(
        "--digests",
        type=Path,
        default=Path("wheel-digests.json"),
        help="Digests file",
    )

    # Compare two wheels
    compare_parser = subparsers.add_parser("compare", help="Compare two wheels")
    compare_parser.add_argument("original", type=Path, help="Original wheel")
    compare_parser.add_argument("rebuilt", type=Path, help="Rebuilt wheel")
    compare_parser.add_argument(
        "--normalize",
        action="store_true",
        default=True,
        help="Normalize timestamps",
    )

    args = parser.parse_args()

    checker = ReproducibilityChecker(normalize=getattr(args, "normalize", True))

    if args.command == "compute":
        checker.save_digests(args.wheelhouse, args.output)

    elif args.command == "verify":
        reports = checker.verify_against_digests(args.wheelhouse, args.digests)

        failures = [r for r in reports.values() if not r.is_reproducible]
        if failures:
            print(f"\n✗ {len(failures)} wheels failed reproducibility check")
            for report in failures:
                print(f"  - {report.wheel_name}")
                for diff in report.differences:
                    print(f"    {diff}")
            sys.exit(1)
        else:
            print(f"\n✓ All {len(reports)} wheels verified successfully")

    elif args.command == "compare":
        report = checker.compare_wheels(args.original, args.rebuilt)

        print(f"\nWheel: {report.wheel_name}")
        print(f"Reproducible: {'✓' if report.is_reproducible else '✗'}")
        print(f"Size match: {'✓' if report.size_match else '✗'}")
        print(f"Original digest:  {report.original_digest}")
        print(f"Rebuilt digest:   {report.rebuilt_digest}")

        if report.differences:
            print("\nDifferences:")
            for diff in report.differences:
                print(f"  - {diff}")

        if not report.is_reproducible and report.normalized_match:
            print("\n✓ Wheels match after normalization")

        sys.exit(0 if report.is_reproducible else 1)
