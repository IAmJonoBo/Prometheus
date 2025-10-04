#!/usr/bin/env python3
"""Automation for setting up private PyPI mirrors (devpi/Nexus)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class MirrorType(Enum):
    """Supported private mirror types."""

    DEVPI = "devpi"
    SIMPLE_HTTP = "simple-http"
    NGINX = "nginx"


@dataclass
class MirrorConfig:
    """Configuration for a private PyPI mirror."""

    mirror_type: MirrorType
    host: str = "localhost"
    port: int = 3141
    data_dir: Path | None = None
    user: str = "root"
    password: str = ""
    index_name: str = "offline"


class DevpiMirrorManager:
    """Manager for devpi-based private PyPI mirrors."""

    def __init__(self, config: MirrorConfig):
        """Initialize devpi mirror manager.

        Args:
            config: Mirror configuration
        """
        self.config = config
        self.data_dir = config.data_dir or Path.home() / ".devpi-server"

    def install_devpi(self) -> bool:
        """Install devpi-server if not already installed.

        Returns:
            True if installation succeeded
        """
        try:
            subprocess.run(
                ["devpi-server", "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            print("devpi-server already installed")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Installing devpi-server...")
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "devpi-server",
                        "devpi-client",
                    ],
                    check=True,
                )
                return True
            except subprocess.CalledProcessError as e:
                print(f"Failed to install devpi-server: {e}")
                return False

    def init_server(self) -> bool:
        """Initialize devpi server data directory.

        Returns:
            True if initialization succeeded
        """
        if (self.data_dir / ".serverversion").exists():
            print(f"devpi server already initialized at {self.data_dir}")
            return True

        print(f"Initializing devpi server at {self.data_dir}...")
        try:
            subprocess.run(
                [
                    "devpi-server",
                    "--init",
                    "--serverdir",
                    str(self.data_dir),
                ],
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to initialize devpi server: {e}")
            return False

    def start_server(self, offline: bool = True) -> bool:
        """Start devpi server.

        Args:
            offline: Whether to run in offline mode

        Returns:
            True if server started successfully
        """
        cmd = [
            "devpi-server",
            "--serverdir",
            str(self.data_dir),
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
        ]

        if offline:
            cmd.append("--offline")

        print(f"Starting devpi server on {self.config.host}:{self.config.port}...")
        try:
            # Start in background
            subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Wait for server to start
            time.sleep(2)
            return self._check_server_health()
        except Exception as e:
            print(f"Failed to start devpi server: {e}")
            return False

    def _check_server_health(self) -> bool:
        """Check if devpi server is healthy.

        Returns:
            True if server is responding
        """
        try:
            result = subprocess.run(
                ["devpi", "use", f"http://{self.config.host}:{self.config.port}"],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def create_index(self) -> bool:
        """Create offline index in devpi.

        Returns:
            True if index was created successfully
        """
        base_url = f"http://{self.config.host}:{self.config.port}"

        try:
            # Set devpi server URL
            subprocess.run(["devpi", "use", base_url], check=True)

            # Login
            subprocess.run(
                [
                    "devpi",
                    "login",
                    self.config.user,
                    "--password",
                    self.config.password,
                ],
                check=True,
            )

            # Create index if it doesn't exist
            result = subprocess.run(
                [
                    "devpi",
                    "index",
                    "-c",
                    self.config.index_name,
                    "volatile=False",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                print(f"Created index: {self.config.user}/{self.config.index_name}")
            elif "already exists" in result.stderr.lower():
                print(
                    f"Index {self.config.user}/{self.config.index_name} already exists"
                )
            else:
                print(f"Failed to create index: {result.stderr}")
                return False

            # Use the new index
            subprocess.run(
                ["devpi", "use", f"{self.config.user}/{self.config.index_name}"],
                check=True,
            )

            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to create index: {e}")
            return False

    def upload_wheelhouse(self, wheelhouse_dir: Path) -> bool:
        """Upload wheels from wheelhouse to devpi index.

        Args:
            wheelhouse_dir: Directory containing wheels

        Returns:
            True if upload succeeded
        """
        if not wheelhouse_dir.exists():
            print(f"Wheelhouse directory not found: {wheelhouse_dir}")
            return False

        wheels = list(wheelhouse_dir.glob("*.whl"))
        if not wheels:
            print(f"No wheels found in {wheelhouse_dir}")
            return False

        print(f"Uploading {len(wheels)} wheels to devpi...")
        for wheel in wheels:
            try:
                subprocess.run(
                    [
                        "devpi",
                        "upload",
                        "--from-dir",
                        str(wheel.parent),
                        str(wheel.name),
                    ],
                    check=True,
                    capture_output=True,
                )
                print(f"  ✓ {wheel.name}")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ {wheel.name}: {e}")
                # Continue with other wheels

        return True

    def get_client_config(self) -> dict[str, Any]:
        """Get pip configuration for clients.

        Returns:
            Dictionary with pip configuration
        """
        index_url = (
            f"http://{self.config.host}:{self.config.port}/"
            f"{self.config.user}/{self.config.index_name}/simple"
        )

        return {
            "index-url": index_url,
            "trusted-host": self.config.host,
        }

    def generate_pip_conf(self, output_path: Path | None = None) -> Path:
        """Generate pip.conf file for clients.

        Args:
            output_path: Path to write pip.conf (default: ~/.pip/pip.conf)

        Returns:
            Path to generated pip.conf
        """
        if output_path is None:
            output_path = Path.home() / ".pip" / "pip.conf"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        config = self.get_client_config()
        content = "[global]\n"
        for key, value in config.items():
            content += f"{key} = {value}\n"

        output_path.write_text(content)
        print(f"Generated pip configuration: {output_path}")
        return output_path


class SimpleHTTPMirror:
    """Simple HTTP server for serving wheelhouse."""

    def __init__(self, config: MirrorConfig):
        """Initialize simple HTTP mirror.

        Args:
            config: Mirror configuration
        """
        self.config = config

    def start_server(self, wheelhouse_dir: Path) -> bool:
        """Start simple HTTP server.

        Args:
            wheelhouse_dir: Directory containing wheels

        Returns:
            True if server started
        """
        if not wheelhouse_dir.exists():
            print(f"Wheelhouse directory not found: {wheelhouse_dir}")
            return False

        print(
            f"Starting HTTP server on {self.config.host}:{self.config.port} "
            f"serving {wheelhouse_dir}"
        )

        try:
            import http.server
            import os

            os.chdir(wheelhouse_dir)
            handler = http.server.SimpleHTTPRequestHandler
            httpd = http.server.HTTPServer(
                (self.config.host, self.config.port), handler
            )
            httpd.serve_forever()
            return True
        except Exception as e:
            print(f"Failed to start HTTP server: {e}")
            return False


def setup_private_mirror(
    mirror_type: MirrorType,
    wheelhouse_dir: Path,
    config: MirrorConfig | None = None,
) -> bool:
    """Setup and configure a private PyPI mirror.

    Args:
        mirror_type: Type of mirror to setup
        wheelhouse_dir: Directory containing wheels to serve
        config: Optional custom configuration

    Returns:
        True if setup succeeded
    """
    if config is None:
        config = MirrorConfig(mirror_type=mirror_type)

    if mirror_type == MirrorType.DEVPI:
        manager = DevpiMirrorManager(config)

        # Install devpi
        if not manager.install_devpi():
            return False

        # Initialize server
        if not manager.init_server():
            return False

        # Start server
        if not manager.start_server():
            return False

        # Create index
        if not manager.create_index():
            return False

        # Upload wheelhouse
        if not manager.upload_wheelhouse(wheelhouse_dir):
            return False

        # Generate client config
        manager.generate_pip_conf()

        print("\n✓ devpi mirror setup complete!")
        print(f"  Server: http://{config.host}:{config.port}")
        print(f"  Index: {config.user}/{config.index_name}")
        print("\nClient setup:")
        print(
            f"  pip config set global.index-url http://{config.host}:{config.port}/{config.user}/{config.index_name}/simple"
        )
        print(f"  pip config set global.trusted-host {config.host}")

        return True

    elif mirror_type == MirrorType.SIMPLE_HTTP:
        manager = SimpleHTTPMirror(config)
        return manager.start_server(wheelhouse_dir)

    else:
        print(f"Unsupported mirror type: {mirror_type}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Setup private PyPI mirror for air-gapped deployments"
    )
    parser.add_argument(
        "--type",
        choices=["devpi", "simple-http"],
        default="devpi",
        help="Mirror type to setup",
    )
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        default=Path("vendor/wheelhouse"),
        help="Path to wheelhouse directory",
    )
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=3141, help="Server port")
    parser.add_argument("--data-dir", type=Path, help="Data directory for mirror")

    args = parser.parse_args()

    config = MirrorConfig(
        mirror_type=MirrorType(args.type),
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
    )

    success = setup_private_mirror(
        mirror_type=MirrorType(args.type),
        wheelhouse_dir=args.wheelhouse,
        config=config,
    )

    sys.exit(0 if success else 1)
