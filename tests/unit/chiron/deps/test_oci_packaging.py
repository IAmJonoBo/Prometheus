"""Tests for OCI packaging."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from chiron.deps.oci_packaging import (
    OCIArtifactMetadata,
    OCIPackager,
    package_wheelhouse_as_oci,
)


@pytest.fixture
def wheelhouse_bundle(tmp_path):
    """Create a test wheelhouse bundle."""
    bundle = tmp_path / "wheelhouse-bundle.tar.gz"
    # Create a minimal tar.gz file
    import tarfile
    with tarfile.open(bundle, "w:gz") as tar:
        # Add a dummy file
        info = tarfile.TarInfo(name="README.txt")
        info.size = 11
        tar.addfile(info, fileobj=None)
    
    return bundle


@pytest.fixture
def sbom_file(tmp_path):
    """Create a test SBOM file."""
    sbom = tmp_path / "sbom.json"
    sbom.write_text('{"bomFormat": "CycloneDX", "specVersion": "1.4"}')
    return sbom


def test_oci_packager_init():
    """Test OCIPackager initialization."""
    packager = OCIPackager(registry="ghcr.io")
    
    assert packager.registry == "ghcr.io"


@patch("chiron.deps.oci_packaging.subprocess.run")
def test_check_oras_installed_success(mock_run):
    """Test checking if ORAS is installed."""
    mock_run.return_value = Mock(
        returncode=0,
        stdout="oras 1.0.0",
        stderr="",
    )
    
    packager = OCIPackager()
    result = packager.check_oras_installed()
    
    assert result is True


@patch("chiron.deps.oci_packaging.subprocess.run")
def test_check_oras_not_installed(mock_run):
    """Test when ORAS is not installed."""
    mock_run.side_effect = FileNotFoundError()
    
    packager = OCIPackager()
    result = packager.check_oras_installed()
    
    assert result is False


def test_create_oci_artifact(tmp_path, wheelhouse_bundle):
    """Test creating OCI artifact layout."""
    packager = OCIPackager()
    
    output_dir = tmp_path / "oci-layout"
    result = packager.create_oci_artifact(
        wheelhouse_bundle=wheelhouse_bundle,
        output_dir=output_dir,
    )
    
    assert result == output_dir
    assert (output_dir / "oci-layout").exists()
    assert (output_dir / "index.json").exists()
    assert (output_dir / "blobs" / "sha256").exists()


def test_create_oci_artifact_with_sbom(tmp_path, wheelhouse_bundle, sbom_file):
    """Test creating OCI artifact with SBOM."""
    packager = OCIPackager()
    
    output_dir = tmp_path / "oci-layout"
    result = packager.create_oci_artifact(
        wheelhouse_bundle=wheelhouse_bundle,
        sbom_path=sbom_file,
        output_dir=output_dir,
    )
    
    assert result == output_dir
    
    # Check index contains manifest
    import json
    index = json.loads((output_dir / "index.json").read_text())
    assert "manifests" in index
    assert len(index["manifests"]) == 1


@patch("chiron.deps.oci_packaging.subprocess.run")
def test_push_to_registry(mock_run, tmp_path, wheelhouse_bundle):
    """Test pushing to registry."""
    mock_run.side_effect = [
        Mock(returncode=0, stdout="oras 1.0.0", stderr=""),  # version check
        Mock(
            returncode=0,
            stdout="Pushed to registry\nDigest: sha256:abc123",
            stderr="",
        ),  # push
    ]
    
    packager = OCIPackager(registry="ghcr.io")
    
    # Create OCI layout first
    oci_layout = packager.create_oci_artifact(
        wheelhouse_bundle=wheelhouse_bundle,
        output_dir=tmp_path / "oci-layout",
    )
    
    metadata = packager.push_to_registry(
        artifact_path=oci_layout,
        repository="org/wheelhouse",
        tag="latest",
    )
    
    assert metadata.name == "org/wheelhouse"
    assert metadata.tag == "latest"
    assert metadata.digest == "sha256:abc123"


@patch("chiron.deps.oci_packaging.subprocess.run")
def test_pull_from_registry(mock_run, tmp_path):
    """Test pulling from registry."""
    mock_run.side_effect = [
        Mock(returncode=0, stdout="oras 1.0.0", stderr=""),  # version check
        Mock(returncode=0, stdout="", stderr=""),  # pull
    ]
    
    packager = OCIPackager(registry="ghcr.io")
    
    output_dir = packager.pull_from_registry(
        repository="org/wheelhouse",
        tag="latest",
        output_dir=tmp_path / "downloaded",
    )
    
    assert output_dir == tmp_path / "downloaded"
    assert output_dir.exists()


def test_oci_artifact_metadata():
    """Test OCIArtifactMetadata dataclass."""
    metadata = OCIArtifactMetadata(
        name="org/wheelhouse",
        tag="v1.0.0",
        registry="ghcr.io",
        digest="sha256:abc123",
    )
    
    assert metadata.name == "org/wheelhouse"
    assert metadata.tag == "v1.0.0"
    assert metadata.registry == "ghcr.io"
    assert metadata.digest == "sha256:abc123"


def test_media_types():
    """Test OCI media type constants."""
    packager = OCIPackager()
    
    assert "wheelhouse" in packager.WHEELHOUSE_MEDIA_TYPE.lower()
    assert "cyclonedx" in packager.SBOM_MEDIA_TYPE.lower()
    assert "osv" in packager.OSV_MEDIA_TYPE.lower()
    assert "in-toto" in packager.PROVENANCE_MEDIA_TYPE.lower()
