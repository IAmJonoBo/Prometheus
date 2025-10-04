"""Utility helpers for installing and inspecting the uv binary."""

from __future__ import annotations

import http.client
import logging
import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Final

LOGGER = logging.getLogger(__name__)

INSTALL_SCRIPT_URL: Final[str] = "https://astral.sh/uv/install.sh"
_POSIX_BINARY_NAME: Final[str] = "uv"
_WINDOWS_BINARY_NAME: Final[str] = "uv.exe"


def _binary_name() -> str:
    return _WINDOWS_BINARY_NAME if sys.platform == "win32" else _POSIX_BINARY_NAME


def ensure_uv_binary(
    target_dir: Path,
    *,
    script_url: str = INSTALL_SCRIPT_URL,
    force: bool = False,
) -> Path:
    """Ensure the uv binary is present in ``target_dir``.

    Downloads and executes Astral's installer script to stage the binary. On
    Windows the installer is not yet automated; callers should fall back to
    manual installation.
    """

    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    binary_path = target_dir / _binary_name()
    if binary_path.exists() and not force:
        LOGGER.debug("uv binary already present at %s", binary_path)
        return binary_path

    if sys.platform == "win32":  # pragma: no cover - requires Windows host
        raise RuntimeError(
            "Automatic uv installation is not supported on Windows; install manually."
        )

    with tempfile.TemporaryDirectory(prefix="uv-install-") as tmp_dir:
        script_path = Path(tmp_dir) / "install.sh"
        parsed = urllib.parse.urlparse(script_url)
        if parsed.scheme != "https":
            raise RuntimeError(f"Blocked non-HTTPS installer URL: {script_url}")

        connection = http.client.HTTPSConnection(parsed.netloc)
        request_path = parsed.path or "/"
        if parsed.query:
            request_path = f"{request_path}?{parsed.query}"
        try:
            connection.request(
                "GET",
                request_path,
                headers={"User-Agent": "chiron-uv-installer"},
            )
            response = connection.getresponse()
            if response.status >= 400:  # pragma: no cover - network failure
                raise RuntimeError(
                    f"uv installer download returned HTTP {response.status}: {response.reason}"
                )
            script_path.write_bytes(response.read())
        finally:
            connection.close()

        script_path.chmod(0o755)
        env = os.environ.copy()
        env.setdefault("UV_NO_MODIFY_PATH", "1")
        command = [
            "sh",
            str(script_path),
            "--",
            f"--install-dir={target_dir}",
            f"--bin-dir={target_dir}",
            "--force",
        ]
        LOGGER.info("Installing uv into %s", target_dir)
        subprocess.run(command, check=True, env=env)  # noqa: S603

    if not binary_path.exists():  # pragma: no cover - defensive guard
        raise RuntimeError(f"uv binary not found at {binary_path}")

    binary_path.chmod(0o755)
    return binary_path


def get_uv_version(binary: Path) -> str | None:
    """Return the uv version string for ``binary`` or ``None`` if unavailable."""

    try:
        result = subprocess.run(  # noqa: S603
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
    ):  # pragma: no cover - runtime failure
        return None

    output = (result.stdout or "").strip()
    for token in output.split():
        if token and token[0].isdigit():
            return token
    return None
