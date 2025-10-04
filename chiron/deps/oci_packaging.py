#!/usr/bin/env python3
"""OCI packaging support for wheelhouse bundles.

This module provides functionality to package wheelhouse bundles as OCI artifacts
that can be pushed to container registries like GHCR, DockerHub, or Artifactory.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OCIManifest:
    """OCI artifact manifest."""

    schema_version: int = 2
    media_type: str = "application/vnd.oci.image.manifest.v1+json"
    config: dict[str, Any] = field(default_factory=dict)
    layers: list[dict[str, Any]] = field(default_factory=list)
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass
class OCIArtifactMetadata:
    """Metadata for an OCI artifact."""

    name: str
    tag: str
    registry: str
    digest: str = ""
    size: int = 0
    created_at: str = ""
    annotations: dict[str, str] = field(default_factory=dict)


class OCIPackager:
    """Package wheelhouse bundles as OCI artifacts."""

    WHEELHOUSE_MEDIA_TYPE = "application/vnd.prometheus.wheelhouse.v1.tar+gzip"
    SBOM_MEDIA_TYPE = "application/vnd.cyclonedx+json"
    OSV_MEDIA_TYPE = "application/vnd.osv.json"
    PROVENANCE_MEDIA_TYPE = "application/vnd.in-toto+json"

    def __init__(self, registry: str = "ghcr.io"):
        """Initialize OCI packager.

        Args:
            registry: OCI registry URL (e.g., ghcr.io, docker.io)
        """
        self.registry = registry

    def check_oras_installed(self) -> bool:
        """Check if ORAS CLI is installed.

        Returns:
            True if ORAS is available
        """
        try:
            result = subprocess.run(
                ["oras", "version"],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"ORAS version: {result.stdout.strip()}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("ORAS not installed. Install from: https://oras.land/")
            print("  brew install oras  # macOS")
            print("  # Or download from https://github.com/oras-project/oras/releases")
            return False

    def create_oci_artifact(
        self,
        wheelhouse_bundle: Path,
        sbom_path: Path | None = None,
        osv_path: Path | None = None,
        provenance_path: Path | None = None,
        output_dir: Path | None = None,
    ) -> Path:
        """Create OCI artifact layout from wheelhouse bundle and metadata.

        Args:
            wheelhouse_bundle: Path to wheelhouse tar.gz bundle
            sbom_path: Path to SBOM JSON file
            osv_path: Path to OSV scan results
            provenance_path: Path to SLSA provenance
            output_dir: Directory to store OCI layout (default: ./oci-layout)

        Returns:
            Path to OCI layout directory
        """
        if output_dir is None:
            output_dir = Path("oci-layout")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Create OCI layout structure
        layout_file = output_dir / "oci-layout"
        layout_file.write_text(json.dumps({"imageLayoutVersion": "1.0.0"}))

        # Create blobs directory
        blobs_dir = output_dir / "blobs" / "sha256"
        blobs_dir.mkdir(parents=True, exist_ok=True)

        layers = []

        # Add wheelhouse bundle layer
        bundle_digest = self._add_blob(wheelhouse_bundle, blobs_dir)
        layers.append(
            {
                "mediaType": self.WHEELHOUSE_MEDIA_TYPE,
                "digest": f"sha256:{bundle_digest}",
                "size": wheelhouse_bundle.stat().st_size,
                "annotations": {
                    "org.opencontainers.image.title": "wheelhouse-bundle.tar.gz",
                },
            }
        )

        # Add SBOM layer if provided
        if sbom_path and sbom_path.exists():
            sbom_digest = self._add_blob(sbom_path, blobs_dir)
            layers.append(
                {
                    "mediaType": self.SBOM_MEDIA_TYPE,
                    "digest": f"sha256:{sbom_digest}",
                    "size": sbom_path.stat().st_size,
                    "annotations": {
                        "org.opencontainers.image.title": "sbom.json",
                    },
                }
            )

        # Add OSV scan results if provided
        if osv_path and osv_path.exists():
            osv_digest = self._add_blob(osv_path, blobs_dir)
            layers.append(
                {
                    "mediaType": self.OSV_MEDIA_TYPE,
                    "digest": f"sha256:{osv_digest}",
                    "size": osv_path.stat().st_size,
                    "annotations": {
                        "org.opencontainers.image.title": "osv-scan.json",
                    },
                }
            )

        # Add provenance if provided
        if provenance_path and provenance_path.exists():
            prov_digest = self._add_blob(provenance_path, blobs_dir)
            layers.append(
                {
                    "mediaType": self.PROVENANCE_MEDIA_TYPE,
                    "digest": f"sha256:{prov_digest}",
                    "size": provenance_path.stat().st_size,
                    "annotations": {
                        "org.opencontainers.image.title": "slsa-provenance.json",
                    },
                }
            )

        # Create config blob
        config = {
            "created": "",
            "architecture": "amd64",
            "os": "linux",
            "config": {},
            "rootfs": {"type": "layers", "diff_ids": []},
            "history": [{"created": "", "created_by": "chiron wheelhouse bundler"}],
        }

        config_json = json.dumps(config).encode()
        config_digest = hashlib.sha256(config_json).hexdigest()
        (blobs_dir / config_digest).write_bytes(config_json)

        # Create manifest
        manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": f"sha256:{config_digest}",
                "size": len(config_json),
            },
            "layers": layers,
            "annotations": {
                "org.opencontainers.image.created": "",
                "org.opencontainers.image.authors": "Prometheus Chiron",
                "org.opencontainers.image.title": "Wheelhouse Bundle",
                "org.opencontainers.image.description": "Offline Python wheelhouse bundle",
            },
        }

        manifest_json = json.dumps(manifest, indent=2).encode()
        manifest_digest = hashlib.sha256(manifest_json).hexdigest()
        (blobs_dir / manifest_digest).write_bytes(manifest_json)

        # Create index
        index = {
            "schemaVersion": 2,
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": f"sha256:{manifest_digest}",
                    "size": len(manifest_json),
                }
            ],
        }

        index_file = output_dir / "index.json"
        index_file.write_text(json.dumps(index, indent=2))

        print(f"✓ Created OCI layout: {output_dir}")
        return output_dir

    def _add_blob(self, file_path: Path, blobs_dir: Path) -> str:
        """Add file as blob to OCI layout.

        Args:
            file_path: Path to file to add
            blobs_dir: Directory for blobs

        Returns:
            SHA256 digest of the file
        """
        content = file_path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        (blobs_dir / digest).write_bytes(content)
        return digest

    def push_to_registry(
        self,
        artifact_path: Path,
        repository: str,
        tag: str = "latest",
        artifact_type: str = "application/vnd.prometheus.wheelhouse.v1.tar+gzip",
    ) -> OCIArtifactMetadata:
        """Push OCI artifact to registry using ORAS.

        Args:
            artifact_path: Path to artifact to push (can be OCI layout or file)
            repository: Repository name (e.g., org/wheelhouse)
            tag: Tag for the artifact
            artifact_type: Media type for the artifact

        Returns:
            Metadata about the pushed artifact
        """
        if not self.check_oras_installed():
            raise RuntimeError("ORAS not installed")

        ref = f"{self.registry}/{repository}:{tag}"

        print(f"Pushing to {ref}...")

        try:
            # If it's an OCI layout directory, push the layout
            if artifact_path.is_dir() and (artifact_path / "oci-layout").exists():
                cmd = [
                    "oras",
                    "push",
                    ref,
                    "--oci-layout",
                    str(artifact_path),
                ]
            else:
                # Push single file
                cmd = [
                    "oras",
                    "push",
                    ref,
                    f"{artifact_path}:{artifact_type}",
                ]

            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )

            print(f"✓ Pushed to {ref}")
            print(result.stdout)

            # Extract digest from output
            digest = ""
            for line in result.stdout.splitlines():
                if "Digest:" in line:
                    digest = line.split("Digest:", 1)[1].strip()
                    break

            return OCIArtifactMetadata(
                name=repository,
                tag=tag,
                registry=self.registry,
                digest=digest,
            )

        except subprocess.CalledProcessError as e:
            print(f"Failed to push artifact: {e.stderr}")
            raise

    def pull_from_registry(
        self,
        repository: str,
        tag: str = "latest",
        output_dir: Path | None = None,
    ) -> Path:
        """Pull OCI artifact from registry using ORAS.

        Args:
            repository: Repository name (e.g., org/wheelhouse)
            tag: Tag for the artifact
            output_dir: Directory to extract files to

        Returns:
            Path to extracted files
        """
        if not self.check_oras_installed():
            raise RuntimeError("ORAS not installed")

        if output_dir is None:
            output_dir = Path("downloaded-wheelhouse")

        output_dir.mkdir(parents=True, exist_ok=True)

        ref = f"{self.registry}/{repository}:{tag}"

        print(f"Pulling from {ref}...")

        try:
            subprocess.run(
                [
                    "oras",
                    "pull",
                    ref,
                    "--output",
                    str(output_dir),
                ],
                check=True,
            )

            print(f"✓ Pulled to {output_dir}")
            return output_dir

        except subprocess.CalledProcessError as e:
            print(f"Failed to pull artifact: {e}")
            raise


def package_wheelhouse_as_oci(
    wheelhouse_bundle: Path,
    repository: str,
    tag: str = "latest",
    registry: str = "ghcr.io",
    sbom_path: Path | None = None,
    osv_path: Path | None = None,
    provenance_path: Path | None = None,
    push: bool = False,
) -> OCIArtifactMetadata:
    """Package wheelhouse bundle as OCI artifact and optionally push.

    Args:
        wheelhouse_bundle: Path to wheelhouse tar.gz bundle
        repository: Repository name (e.g., org/wheelhouse)
        tag: Tag for the artifact
        registry: OCI registry URL
        sbom_path: Optional SBOM file
        osv_path: Optional OSV scan results
        provenance_path: Optional SLSA provenance
        push: Whether to push to registry

    Returns:
        Metadata about the OCI artifact
    """
    packager = OCIPackager(registry=registry)

    # Create OCI layout
    oci_layout = packager.create_oci_artifact(
        wheelhouse_bundle=wheelhouse_bundle,
        sbom_path=sbom_path,
        osv_path=osv_path,
        provenance_path=provenance_path,
    )

    metadata = OCIArtifactMetadata(
        name=repository,
        tag=tag,
        registry=registry,
    )

    # Push if requested
    if push:
        metadata = packager.push_to_registry(
            artifact_path=oci_layout,
            repository=repository,
            tag=tag,
        )

    return metadata


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Package wheelhouse as OCI artifact")
    parser.add_argument(
        "bundle",
        type=Path,
        help="Path to wheelhouse bundle (tar.gz)",
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="Repository name (e.g., org/wheelhouse)",
    )
    parser.add_argument(
        "--tag",
        default="latest",
        help="Tag for the artifact",
    )
    parser.add_argument(
        "--registry",
        default="ghcr.io",
        help="OCI registry URL",
    )
    parser.add_argument(
        "--sbom",
        type=Path,
        help="Path to SBOM file",
    )
    parser.add_argument(
        "--osv",
        type=Path,
        help="Path to OSV scan results",
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        help="Path to SLSA provenance",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push to registry after creating",
    )

    args = parser.parse_args()

    try:
        metadata = package_wheelhouse_as_oci(
            wheelhouse_bundle=args.bundle,
            repository=args.repository,
            tag=args.tag,
            registry=args.registry,
            sbom_path=args.sbom,
            osv_path=args.osv,
            provenance_path=args.provenance,
            push=args.push,
        )

        print("\n✓ OCI artifact created:")
        print(f"  Repository: {metadata.registry}/{metadata.name}")
        print(f"  Tag: {metadata.tag}")
        if metadata.digest:
            print(f"  Digest: {metadata.digest}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
