"""CLI helper to ensure the uv binary is installed locally."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from chiron.tools import uv_installer

LOGGER = logging.getLogger(__name__)


def _default_install_dir() -> Path:
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "Astral" / "uv" / "bin"
    return Path.home() / ".local" / "bin"


def _vendor_binary_path(vendor_dir: Path) -> Path:
    binary_name = "uv.exe" if sys.platform == "win32" else "uv"
    return vendor_dir / binary_name


def _install_from_vendor(vendor_dir: Path, target_dir: Path, *, force: bool) -> Path:
    vendor_dir = vendor_dir.expanduser().resolve()
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    source = _vendor_binary_path(vendor_dir)
    if not source.exists():
        raise FileNotFoundError(f"uv bundle not found at {source}")

    destination = target_dir / source.name
    if destination.exists() and not force:
        LOGGER.info(
            "uv already present at %s; skipping (use --force to overwrite)", destination
        )
        return destination

    shutil.copy2(source, destination)
    destination.chmod(0o755)
    return destination


def run(
    install_dir: Path | None = None,
    *,
    from_vendor: bool = False,
    vendor_dir: Path | None = None,
    force: bool = False,
    script_url: str | None = None,
    verbose: bool = False,
) -> int:
    if verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    target_dir = (install_dir or _default_install_dir()).expanduser().resolve()
    try:
        if from_vendor:
            vendor = (vendor_dir or Path("vendor/uv")).expanduser().resolve()
            binary_path = _install_from_vendor(vendor, target_dir, force=force)
        else:
            binary_path = uv_installer.ensure_uv_binary(
                target_dir,
                script_url=script_url or uv_installer.INSTALL_SCRIPT_URL,
                force=force,
            )
    except Exception as exc:  # pragma: no cover - command line feedback
        LOGGER.error("Failed to install uv: %s", exc)
        return 1

    version = uv_installer.get_uv_version(binary_path)
    LOGGER.info("uv installed at %s (version %s)", binary_path, version or "unknown")
    print(f"uv installed at {binary_path} (version {version or 'unknown'})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or update the uv binary")
    parser.add_argument(
        "--install-dir", type=Path, help="Directory to place the uv binary"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite uv if it already exists at the target location",
    )
    parser.add_argument(
        "--from-vendor",
        action="store_true",
        help="Install uv from the vendor bundle instead of downloading",
    )
    parser.add_argument(
        "--vendor-dir",
        type=Path,
        default=Path("vendor/uv"),
        help="Location of the vendor uv bundle",
    )
    parser.add_argument(
        "--script-url",
        help="Override the installer script URL (default: Astral upstream)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(
        install_dir=args.install_dir,
        from_vendor=args.from_vendor,
        vendor_dir=args.vendor_dir,
        force=args.force,
        script_url=args.script_url,
        verbose=args.verbose,
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
