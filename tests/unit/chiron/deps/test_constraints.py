"""Tests for hash-pinned constraints generation."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from chiron.deps.constraints import (
    ConstraintsConfig,
    ConstraintsGenerator,
    generate_constraints,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "test_project"
    project.mkdir()

    # Create minimal pyproject.toml
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "test-project"
version = "0.1.0"
dependencies = ["requests>=2.28.0"]
"""
    )

    return project


def test_constraints_config_creation(temp_project: Path):
    """Test ConstraintsConfig creation."""
    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "constraints.txt",
        tool="uv",
        generate_hashes=True,
        include_extras=["dev"],
        python_version="3.12",
    )

    assert config.project_root == temp_project
    assert config.tool == "uv"
    assert config.generate_hashes is True
    assert config.include_extras == ["dev"]


def test_constraints_generator_init(temp_project: Path):
    """Test ConstraintsGenerator initialization."""
    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "constraints.txt",
    )

    generator = ConstraintsGenerator(config)
    assert generator.config == config


@patch("chiron.deps.constraints.shutil.which")
@patch("chiron.deps.constraints.subprocess.run")
def test_generate_with_uv_success(
    mock_run: Mock,
    mock_which: Mock,
    temp_project: Path,
):
    """Test successful generation with uv."""
    mock_which.return_value = "/usr/bin/uv"
    mock_run.return_value = Mock(returncode=0, stderr="")

    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "constraints.txt",
        tool="uv",
        generate_hashes=True,
    )

    # Create output file
    config.output_path.write_text("requests==2.28.0 --hash=sha256:abc123")

    generator = ConstraintsGenerator(config)
    result = generator.generate()

    assert result is True
    mock_run.assert_called_once()

    # Verify command includes --generate-hashes
    call_args = mock_run.call_args
    assert "--generate-hashes" in call_args[0][0]


@patch("chiron.deps.constraints.shutil.which")
def test_generate_with_uv_not_found(mock_which: Mock, temp_project: Path):
    """Test failure when uv not found."""
    mock_which.return_value = None

    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "constraints.txt",
        tool="uv",
    )

    generator = ConstraintsGenerator(config)
    result = generator.generate()

    assert result is False


@patch("chiron.deps.constraints.shutil.which")
@patch("chiron.deps.constraints.subprocess.run")
def test_generate_with_extras(
    mock_run: Mock,
    mock_which: Mock,
    temp_project: Path,
):
    """Test generation with extras."""
    mock_which.return_value = "/usr/bin/uv"
    mock_run.return_value = Mock(returncode=0, stderr="")

    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "constraints.txt",
        tool="uv",
        include_extras=["dev", "test"],
    )

    config.output_path.write_text("requests==2.28.0")

    generator = ConstraintsGenerator(config)
    generator.generate()

    # Verify command includes --extra flags
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "--extra" in cmd
    assert "dev" in cmd
    assert "test" in cmd


def test_verify_hashes_with_hashes(temp_project: Path):
    """Test hash verification with hashes present."""
    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "constraints.txt",
    )

    # Create file with hashes
    config.output_path.write_text(
        """
requests==2.28.0 \\
    --hash=sha256:abc123 \\
    --hash=sha256:def456
certifi==2023.7.22 \\
    --hash=sha256:789xyz
"""
    )

    generator = ConstraintsGenerator(config)
    result = generator.verify_hashes()

    assert result is True


def test_verify_hashes_without_hashes(temp_project: Path):
    """Test hash verification without hashes."""
    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "constraints.txt",
    )

    # Create file without hashes
    config.output_path.write_text(
        """
requests==2.28.0
certifi==2023.7.22
"""
    )

    generator = ConstraintsGenerator(config)
    result = generator.verify_hashes()

    assert result is False


def test_verify_hashes_file_not_found(temp_project: Path):
    """Test hash verification when file doesn't exist."""
    config = ConstraintsConfig(
        project_root=temp_project,
        pyproject_path=temp_project / "pyproject.toml",
        output_path=temp_project / "nonexistent.txt",
    )

    generator = ConstraintsGenerator(config)
    result = generator.verify_hashes()

    assert result is False


@patch("chiron.deps.constraints.ConstraintsGenerator")
def test_generate_constraints_convenience_function(
    mock_generator_class: Mock,
    temp_project: Path,
):
    """Test convenience function."""
    mock_generator = MagicMock()
    mock_generator.generate.return_value = True
    mock_generator.verify_hashes.return_value = True
    mock_generator_class.return_value = mock_generator

    result = generate_constraints(
        project_root=temp_project,
        tool="uv",
        include_extras=["dev"],
    )

    assert result is True
    mock_generator.generate.assert_called_once()
    mock_generator.verify_hashes.assert_called_once()
