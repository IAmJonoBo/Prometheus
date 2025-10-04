#!/usr/bin/env python3
"""
Wheelhouse bundle generation for offline/air-gapped deployments.

Creates portable wheelhouse bundles with:
- All wheel files
- requirements.txt
- SHA256 checksums
- Simple index for pip
- Metadata and provenance
"""

from __future__ import annotations

import hashlib
import json
import logging
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BundleMetadata:
    """Metadata for a wheelhouse bundle."""
    
    created_at: str
    commit_sha: str | None = None
    git_ref: str | None = None
    python_version: str | None = None
    platform: str | None = None
    wheel_count: int = 0
    total_size_bytes: int = 0
    checksums: dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "created_at": self.created_at,
            "commit_sha": self.commit_sha,
            "git_ref": self.git_ref,
            "python_version": self.python_version,
            "platform": self.platform,
            "wheel_count": self.wheel_count,
            "total_size_bytes": self.total_size_bytes,
            "checksums": dict(self.checksums),
        }


class WheelhouseBundler:
    """Create portable wheelhouse bundles."""
    
    def __init__(self, wheelhouse_dir: Path):
        """
        Initialize bundler.
        
        Args:
            wheelhouse_dir: Directory containing wheels
        """
        self.wheelhouse_dir = wheelhouse_dir
        
        if not wheelhouse_dir.exists():
            raise ValueError(f"Wheelhouse directory not found: {wheelhouse_dir}")
    
    def create_bundle(
        self,
        output_path: Path,
        include_sbom: bool = True,
        include_osv: bool = True,
        commit_sha: str | None = None,
        git_ref: str | None = None,
    ) -> BundleMetadata:
        """
        Create a portable wheelhouse bundle.
        
        Args:
            output_path: Path for output bundle (tar.gz)
            include_sbom: Include SBOM file if present
            include_osv: Include OSV scan results if present
            commit_sha: Git commit SHA
            git_ref: Git reference (branch/tag)
        
        Returns:
            BundleMetadata
        """
        logger.info(f"Creating wheelhouse bundle: {output_path}")
        
        # Collect wheels
        wheels = list(self.wheelhouse_dir.glob("*.whl"))
        if not wheels:
            raise ValueError(f"No wheels found in {self.wheelhouse_dir}")
        
        logger.info(f"Found {len(wheels)} wheels")
        
        # Generate checksums
        checksums = self._generate_checksums(wheels)
        
        # Generate simple index
        simple_index_html = self._generate_simple_index(wheels)
        
        # Create metadata
        metadata = BundleMetadata(
            created_at=datetime.now(UTC).isoformat(),
            commit_sha=commit_sha,
            git_ref=git_ref,
            wheel_count=len(wheels),
            total_size_bytes=sum(w.stat().st_size for w in wheels),
            checksums=checksums,
        )
        
        # Write metadata file
        metadata_path = self.wheelhouse_dir / "bundle-metadata.json"
        metadata_path.write_text(json.dumps(metadata.to_dict(), indent=2))
        
        # Write checksums file
        checksums_path = self.wheelhouse_dir / "SHA256SUMS"
        self._write_checksums_file(checksums_path, checksums)
        
        # Write simple index
        simple_index_path = self.wheelhouse_dir / "simple" / "index.html"
        simple_index_path.parent.mkdir(parents=True, exist_ok=True)
        simple_index_path.write_text(simple_index_html)
        
        # Create package-specific index pages
        self._create_package_indexes(wheels)
        
        # Create tarball
        with tarfile.open(output_path, "w:gz") as tar:
            # Add all wheels
            for wheel in wheels:
                tar.add(wheel, arcname=f"wheelhouse/{wheel.name}")
            
            # Add metadata and checksums
            tar.add(metadata_path, arcname="wheelhouse/bundle-metadata.json")
            tar.add(checksums_path, arcname="wheelhouse/SHA256SUMS")
            
            # Add simple index
            simple_dir = self.wheelhouse_dir / "simple"
            if simple_dir.exists():
                for item in simple_dir.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(self.wheelhouse_dir)
                        tar.add(item, arcname=f"wheelhouse/{rel_path}")
            
            # Add SBOM if present
            if include_sbom:
                sbom_path = self.wheelhouse_dir / "sbom.json"
                if sbom_path.exists():
                    tar.add(sbom_path, arcname="wheelhouse/sbom.json")
            
            # Add OSV scan if present
            if include_osv:
                osv_path = self.wheelhouse_dir / "osv.json"
                if osv_path.exists():
                    tar.add(osv_path, arcname="wheelhouse/osv.json")
            
            # Add requirements.txt if present
            req_path = self.wheelhouse_dir / "requirements.txt"
            if req_path.exists():
                tar.add(req_path, arcname="wheelhouse/requirements.txt")
        
        # Generate bundle checksum
        bundle_checksum = self._calculate_file_checksum(output_path)
        checksum_file = output_path.with_suffix(output_path.suffix + ".sha256")
        checksum_file.write_text(f"{bundle_checksum}  {output_path.name}\n")
        
        logger.info(f"Created bundle: {output_path}")
        logger.info(f"Bundle checksum: {bundle_checksum}")
        
        return metadata
    
    def _generate_checksums(self, wheels: list[Path]) -> dict[str, str]:
        """Generate SHA256 checksums for all wheels."""
        logger.info("Generating checksums...")
        checksums = {}
        
        for wheel in wheels:
            checksum = self._calculate_file_checksum(wheel)
            checksums[wheel.name] = checksum
        
        return checksums
    
    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _write_checksums_file(
        self,
        output_path: Path,
        checksums: dict[str, str],
    ) -> None:
        """Write checksums to a file in standard format."""
        with output_path.open("w") as f:
            for filename, checksum in sorted(checksums.items()):
                f.write(f"{checksum}  {filename}\n")
    
    def _generate_simple_index(self, wheels: list[Path]) -> str:
        """Generate simple PyPI-compatible index HTML."""
        # Group wheels by package name
        packages: dict[str, list[Path]] = {}
        for wheel in wheels:
            # Extract package name from wheel filename
            # Format: {package}-{version}-{python}-{abi}-{platform}.whl
            parts = wheel.stem.split("-")
            if len(parts) >= 2:
                pkg_name = parts[0].lower()
                packages.setdefault(pkg_name, []).append(wheel)
        
        # Generate index HTML
        html = "<!DOCTYPE html>\n<html>\n<head><title>Simple Index</title></head>\n<body>\n"
        for pkg_name in sorted(packages.keys()):
            html += f'<a href="{pkg_name}/">{pkg_name}</a><br/>\n'
        html += "</body>\n</html>\n"
        
        return html
    
    def _create_package_indexes(self, wheels: list[Path]) -> None:
        """Create package-specific index pages."""
        # Group wheels by package name
        packages: dict[str, list[Path]] = {}
        for wheel in wheels:
            parts = wheel.stem.split("-")
            if len(parts) >= 2:
                pkg_name = parts[0].lower()
                packages.setdefault(pkg_name, []).append(wheel)
        
        simple_dir = self.wheelhouse_dir / "simple"
        
        for pkg_name, pkg_wheels in packages.items():
            pkg_dir = simple_dir / pkg_name
            pkg_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate package index HTML
            html = f"<!DOCTYPE html>\n<html>\n<head><title>Links for {pkg_name}</title></head>\n<body>\n"
            html += f"<h1>Links for {pkg_name}</h1>\n"
            
            for wheel in sorted(pkg_wheels):
                html += f'<a href="../../{wheel.name}">{wheel.name}</a><br/>\n'
            
            html += "</body>\n</html>\n"
            
            index_path = pkg_dir / "index.html"
            index_path.write_text(html)


def create_wheelhouse_bundle(
    wheelhouse_dir: Path,
    output_path: Path,
    commit_sha: str | None = None,
    git_ref: str | None = None,
) -> BundleMetadata:
    """
    Create a portable wheelhouse bundle.
    
    Args:
        wheelhouse_dir: Directory containing wheels
        output_path: Path for output bundle
        commit_sha: Git commit SHA
        git_ref: Git reference
    
    Returns:
        BundleMetadata
    """
    bundler = WheelhouseBundler(wheelhouse_dir)
    return bundler.create_bundle(
        output_path=output_path,
        commit_sha=commit_sha,
        git_ref=git_ref,
    )
