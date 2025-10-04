"""Tests for private mirror setup."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from chiron.deps.private_mirror import (
    DevpiMirrorManager,
    MirrorConfig,
    MirrorType,
    setup_private_mirror,
)


@pytest.fixture
def mirror_config():
    """Create test mirror configuration."""
    return MirrorConfig(
        mirror_type=MirrorType.DEVPI,
        host="localhost",
        port=3141,
        data_dir=Path("/tmp/test-devpi"),
    )


@pytest.fixture
def wheelhouse_dir(tmp_path):
    """Create a test wheelhouse directory."""
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    # Create mock wheel files
    (wheelhouse / "package1-1.0.0-py3-none-any.whl").write_text("mock wheel 1")
    (wheelhouse / "package2-2.0.0-py3-none-any.whl").write_text("mock wheel 2")

    return wheelhouse


def test_devpi_manager_init(mirror_config):
    """Test DevpiMirrorManager initialization."""
    manager = DevpiMirrorManager(mirror_config)

    assert manager.config == mirror_config
    assert manager.data_dir == mirror_config.data_dir


@patch("chiron.deps.private_mirror.subprocess.run")
def test_check_devpi_installed_success(mock_run, mirror_config):
    """Test checking if devpi is installed."""
    mock_run.return_value = Mock(returncode=0, stdout="devpi-server 6.9.0")

    manager = DevpiMirrorManager(mirror_config)
    result = manager.install_devpi()

    assert result is True
    mock_run.assert_called()


@patch("chiron.deps.private_mirror.subprocess.run")
def test_check_devpi_not_installed(mock_run, mirror_config):
    """Test devpi installation when not present."""
    mock_run.side_effect = [
        FileNotFoundError(),  # devpi-server --version fails
        Mock(returncode=0),  # pip install succeeds
    ]

    manager = DevpiMirrorManager(mirror_config)
    result = manager.install_devpi()

    assert result is True


def test_get_client_config(mirror_config):
    """Test getting client configuration."""
    manager = DevpiMirrorManager(mirror_config)

    config = manager.get_client_config()

    assert "index-url" in config
    assert "localhost:3141" in config["index-url"]
    assert config["trusted-host"] == "localhost"


def test_generate_pip_conf(mirror_config, tmp_path):
    """Test generating pip.conf file."""
    manager = DevpiMirrorManager(mirror_config)

    output_file = tmp_path / "pip.conf"
    result = manager.generate_pip_conf(output_file)

    assert result == output_file
    assert output_file.exists()

    content = output_file.read_text()
    assert "[global]" in content
    assert "index-url" in content
    assert "trusted-host" in content


@patch("chiron.deps.private_mirror.subprocess.run")
def test_init_server(mock_run, mirror_config, tmp_path):
    """Test initializing devpi server."""
    mirror_config.data_dir = tmp_path / "devpi-server"

    mock_run.return_value = Mock(returncode=0)

    manager = DevpiMirrorManager(mirror_config)
    result = manager.init_server()

    assert result is True


@patch("chiron.deps.private_mirror.subprocess.run")
def test_create_index(mock_run, mirror_config):
    """Test creating devpi index."""
    mock_run.return_value = Mock(returncode=0, stderr="", stdout="")

    manager = DevpiMirrorManager(mirror_config)
    result = manager.create_index()

    assert result is True


@patch("chiron.deps.private_mirror.subprocess.run")
def test_upload_wheelhouse(mock_run, mirror_config, wheelhouse_dir):
    """Test uploading wheelhouse to devpi."""
    mock_run.return_value = Mock(returncode=0)

    manager = DevpiMirrorManager(mirror_config)
    result = manager.upload_wheelhouse(wheelhouse_dir)

    assert result is True


def test_upload_wheelhouse_no_dir(mirror_config, tmp_path):
    """Test uploading from non-existent directory."""
    manager = DevpiMirrorManager(mirror_config)

    result = manager.upload_wheelhouse(tmp_path / "nonexistent")

    assert result is False


def test_upload_wheelhouse_no_wheels(mirror_config, tmp_path):
    """Test uploading from empty directory."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    manager = DevpiMirrorManager(mirror_config)
    result = manager.upload_wheelhouse(empty_dir)

    assert result is False


def test_mirror_type_enum():
    """Test MirrorType enum."""
    assert MirrorType.DEVPI.value == "devpi"
    assert MirrorType.SIMPLE_HTTP.value == "simple-http"
    assert MirrorType.NGINX.value == "nginx"


def test_mirror_config_defaults():
    """Test MirrorConfig default values."""
    config = MirrorConfig(mirror_type=MirrorType.DEVPI)

    assert config.host == "localhost"
    assert config.port == 3141
    assert config.user == "root"
    assert config.password == ""
