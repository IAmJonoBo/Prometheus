#!/usr/bin/env python3
"""Bootstrap tool for installing dependencies from the offline wheelhouse."""

from __future__ import annotations

import argparse
import contextlib
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import venv
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path

from chiron.packaging.metadata import WheelhouseManifest, load_wheelhouse_manifest
from chiron.tools.uv_installer import get_uv_version

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WHEELHOUSE = REPO_ROOT / "vendor" / "wheelhouse"
DEFAULT_REQUIREMENTS = DEFAULT_WHEELHOUSE / "requirements.txt"
DEFAULT_CONSTRAINTS = REPO_ROOT / "constraints" / "production.txt"
UV_BUNDLE_DIR = "uv"
UV_BINARY_POSIX = "uv"
UV_BINARY_WINDOWS = "uv.exe"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install Prometheus dependencies from the offline wheelhouse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example usage:\n"
            "  python scripts/bootstrap_offline.py\n"
            "  python scripts/bootstrap_offline.py --venv .venv --poetry-bin ~/.local/bin/poetry\n"
            "  python scripts/bootstrap_offline.py --no-poetry --pip-extra-arg --upgrade-strategy eager"
        ),
    )
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        default=DEFAULT_WHEELHOUSE,
        help="Directory containing requirements.txt and cached wheels (default: vendor/wheelhouse)",
    )
    parser.add_argument(
        "--wheelhouse-url",
        help="HTTP(S) URL for a wheelhouse tarball to download when the local directory is missing.",
    )
    parser.add_argument(
        "--models-url",
        help="HTTP(S) URL for a vendor/models tarball to download when the directory is missing.",
    )
    parser.add_argument(
        "--images-url",
        help="HTTP(S) URL for a vendor/images tarball to download when the directory is missing.",
    )
    parser.add_argument(
        "--artifact-token-env",
        default="GITHUB_TOKEN",
        help=(
            "Environment variable holding a token for authenticated downloads "
            "(default: GITHUB_TOKEN)."
        ),
    )
    parser.add_argument(
        "--force-download-wheelhouse",
        action="store_true",
        help="Always download the wheelhouse archive even if the directory exists.",
    )
    parser.add_argument(
        "--force-download-models",
        action="store_true",
        help="Always download the models archive even if the directory exists.",
    )
    parser.add_argument(
        "--force-download-images",
        action="store_true",
        help="Always download the images archive even if the directory exists.",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        help="Path to requirements.txt exported alongside the wheelhouse (default: <wheelhouse>/requirements.txt)",
    )
    parser.add_argument(
        "--constraints",
        type=Path,
        default=DEFAULT_CONSTRAINTS,
        help="Optional pip constraints file (default: constraints/production.txt)",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python interpreter to use for pip installations when --venv is not supplied.",
    )
    parser.add_argument(
        "--venv",
        type=Path,
        help="Optional virtual environment directory to create/use before installing packages.",
    )
    parser.add_argument(
        "--poetry-bin",
        default=os.environ.get("POETRY", "poetry"),
        help="Poetry executable to invoke after populating the environment (default: poetry).",
    )
    parser.add_argument(
        "--no-poetry",
        action="store_true",
        help="Skip the poetry install step (pip sync only).",
    )
    parser.add_argument(
        "--pip-extra-arg",
        action="append",
        dest="pip_extra_args",
        default=None,
        metavar="ARG",
        help="Additional argument to forward to pip install (repeatable).",
    )
    parser.add_argument(
        "--no-pip-upgrade",
        action="store_true",
        help="Do not pass --upgrade to pip install (defaults to upgrading from cached wheels).",
    )
    parser.add_argument(
        "--extras",
        action="append",
        dest="extras",
        default=None,
        metavar="EXTRA",
        help="Override wheelhouse extras to install via poetry (repeatable).",
    )
    parser.add_argument(
        "--include-dev",
        dest="include_dev",
        action="store_true",
        help="Force installation of dev dependency group regardless of wheelhouse manifest.",
    )
    parser.add_argument(
        "--no-dev",
        dest="include_dev",
        action="store_false",
        help="Skip dev dependency group even if wheelhouse manifest enabled it.",
    )
    parser.add_argument(
        "--poetry-args",
        nargs=argparse.REMAINDER,
        help="Additional arguments appended to the poetry install command (after '--').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands without executing them.",
    )
    parser.add_argument(
        "--install-uv",
        dest="install_uv",
        action="store_true",
        help="Install the uv binary from the vendor bundle (default when available).",
    )
    parser.add_argument(
        "--no-install-uv",
        dest="install_uv",
        action="store_false",
        help="Skip uv installation even if a vendor bundle is present.",
    )
    parser.set_defaults(install_uv=None)
    parser.add_argument(
        "--uv-target",
        type=Path,
        help="Directory to copy the uv binary into when installing.",
    )
    parser.add_argument(
        "--uv-force",
        action="store_true",
        help="Overwrite the uv binary at the target location if it already exists.",
    )
    parser.set_defaults(include_dev=None)

    return parser


def _directory_missing_or_empty(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        raise RuntimeError(f"Expected directory at {path}, found file")
    return not any(path.iterdir())


def _download_file(url: str, destination: Path, token: str | None) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in {"", "file"}:
        source_path = Path(urllib.request.url2pathname(parsed.path))
        if not source_path.exists():
            raise RuntimeError(f"Local archive not found: {source_path}")
        shutil.copyfile(source_path, destination)
        return
    if parsed.scheme not in {"https"}:
        raise RuntimeError(f"Blocked non-HTTPS download URL: {url}")

    request = urllib.request.Request(url)  # noqa: S310 - https scheme enforced above
    request.add_header("Accept", "application/octet-stream")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler())
    try:
        with contextlib.closing(opener.open(request)) as response, destination.open("wb") as handle:  # type: ignore[arg-type]
            shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failure
        raise RuntimeError(
            f"Failed to download {url}: HTTP {exc.code} {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network failure
        raise RuntimeError(f"Failed to download {url}: {exc.reason}") from exc


def _extract_tarball(archive: Path, *, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(destination, filter="data")


def _download_and_extract(
    url: str,
    *,
    token: str | None,
    extract_root: Path,
    expected_subdir: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="offline-bootstrap-") as tmp_dir:
        archive_path = Path(tmp_dir) / "archive.tar.gz"
        print(f"Downloading {expected_subdir} archive from {url}")
        _download_file(url, archive_path, token)
        target_dir = extract_root / expected_subdir
        if target_dir.exists():
            shutil.rmtree(target_dir)
        _extract_tarball(archive_path, destination=extract_root)
        if not target_dir.exists():
            raise RuntimeError(
                f"Archive from {url} did not contain expected directory '{expected_subdir}'"
            )


def _vendor_uv_dir(wheelhouse: Path) -> Path:
    return wheelhouse.parent / UV_BUNDLE_DIR


def _default_uv_target(venv_path: Path | None) -> Path:
    if venv_path is not None:
        return venv_path / ("Scripts" if sys.platform == "win32" else "bin")
    if sys.platform == "win32":  # pragma: no cover - platform specific
        return Path.home() / "AppData" / "Local" / "Astral" / "uv" / "bin"
    return Path.home() / ".local" / "bin"


def _install_uv_from_vendor(
    vendor_dir: Path,
    target_dir: Path,
    *,
    force: bool,
    dry_run: bool,
) -> None:
    binary_name = UV_BINARY_WINDOWS if sys.platform == "win32" else UV_BINARY_POSIX
    source = vendor_dir / binary_name
    if not source.exists():
        print(f"uv bundle not found at {source}; skipping installation")
        return

    target_dir = target_dir.expanduser().resolve()
    if dry_run:
        print(f"[dry run] Would install uv into {target_dir}")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / source.name
    if destination.exists() and not force:
        print(
            f"uv already present at {destination}; skipping (use --uv-force to overwrite)."
        )
        return

    shutil.copy2(source, destination)
    destination.chmod(0o755)
    version = get_uv_version(destination)
    print(f"Installed uv {version or 'unknown version'} to {destination}")


def _maybe_install_uv(
    args: argparse.Namespace, wheelhouse: Path, venv_path: Path | None
) -> None:
    vendor_uv_dir = _vendor_uv_dir(wheelhouse)
    install_uv = args.install_uv
    if install_uv is None:
        install_uv = vendor_uv_dir.exists()
    if not install_uv:
        return

    uv_target = args.uv_target or _default_uv_target(venv_path)
    _install_uv_from_vendor(
        vendor_uv_dir,
        uv_target,
        force=args.uv_force,
        dry_run=args.dry_run,
    )


def _maybe_fetch_archives(args: argparse.Namespace) -> None:
    token = None
    if args.artifact_token_env:
        token = os.environ.get(args.artifact_token_env)

    wheelhouse_dir = args.wheelhouse.resolve()
    if args.wheelhouse_url and (
        args.force_download_wheelhouse or _directory_missing_or_empty(wheelhouse_dir)
    ):
        _download_and_extract(
            args.wheelhouse_url,
            token=token,
            extract_root=wheelhouse_dir.parent,
            expected_subdir=wheelhouse_dir.name,
        )

    models_dir = REPO_ROOT / "vendor" / "models"
    if args.models_url and (
        args.force_download_models or _directory_missing_or_empty(models_dir)
    ):
        _download_and_extract(
            args.models_url,
            token=token,
            extract_root=models_dir.parent,
            expected_subdir=models_dir.name,
        )

    images_dir = REPO_ROOT / "vendor" / "images"
    if args.images_url and (
        args.force_download_images or _directory_missing_or_empty(images_dir)
    ):
        _download_and_extract(
            args.images_url,
            token=token,
            extract_root=images_dir.parent,
            expected_subdir=images_dir.name,
        )


def _validate_inputs(
    parser: argparse.ArgumentParser, wheelhouse: Path, requirements: Path
) -> None:
    if not wheelhouse.is_dir():
        parser.error(f"Wheelhouse directory not found: {wheelhouse}")
    if not requirements.is_file():
        parser.error(f"Requirements file not found: {requirements}")


def _report_metadata(
    metadata: WheelhouseManifest, extras: Sequence[str], include_dev: bool
) -> None:
    print("Wheelhouse prepared from commit:", metadata.commit or "<unknown>")
    if metadata.generated_at:
        print("Generated at:", metadata.generated_at)
    if extras:
        print("Installing extras:", ", ".join(extras))
    print("Include dev dependencies:", "yes" if include_dev else "no")


def _load_wheelhouse_metadata(wheelhouse: Path) -> WheelhouseManifest:
    manifest_path = wheelhouse / "manifest.json"
    try:
        return load_wheelhouse_manifest(manifest_path)
    except FileNotFoundError:
        return WheelhouseManifest(
            generated_at=None,
            extras=(),
            include_dev=False,
            create_archive=False,
            commit=None,
        )
    except RuntimeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            f"Failed to parse wheelhouse manifest at {manifest_path}: {exc}"
        ) from exc


def _ensure_virtualenv(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.exists():
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(resolved)
    if sys.platform == "win32":  # pragma: no cover - platform specific
        python_path = resolved / "Scripts" / "python.exe"
    else:
        python_path = resolved / "bin" / "python"
    if (
        not python_path.exists()
    ):  # pragma: no cover - defensive guard for unusual layouts
        raise RuntimeError(f"Python executable not found in virtualenv: {python_path}")
    return python_path


def _prepare_env(
    base_env: Mapping[str, str], wheelhouse: Path, venv_path: Path | None
) -> MutableMapping[str, str]:
    env = dict(base_env)
    env.setdefault("PIP_NO_INDEX", "1")
    env["PIP_FIND_LINKS"] = str(wheelhouse)
    env.setdefault("PIP_ROOT_USER_ACTION", "ignore")
    if venv_path is not None:
        env["VIRTUAL_ENV"] = str(venv_path)
        bin_dir = venv_path / ("Scripts" if sys.platform == "win32" else "bin")
        current_path = env.get("PATH", "")
        env["PATH"] = f"{bin_dir}{os.pathsep}{current_path}"
    return env


def _run_command(
    command: Sequence[str], *, env: Mapping[str, str], dry_run: bool
) -> None:
    rendered = " ".join(shlex.quote(part) for part in command)
    print(f"→ {rendered}")
    if dry_run:
        return
    subprocess.run(  # noqa: S603 - command constructed internally
        command, check=True, env=env
    )


def _execute_with_reporting(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    dry_run: bool,
    label: str,
) -> int:
    try:
        _run_command(command, env=env, dry_run=dry_run)
    except subprocess.CalledProcessError as exc:
        exit_code = exc.returncode or 1
        print(f"{label} failed with exit code {exit_code}")
        return exit_code
    return 0


def _build_pip_command(
    python_executable: Path,
    wheelhouse: Path,
    requirements: Path,
    *,
    upgrade: bool,
    extra_args: Sequence[str] | None,
    constraints: Path | None,
) -> list[str]:
    command: list[str] = [
        str(python_executable),
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse),
    ]
    if upgrade:
        command.append("--upgrade")
    if constraints and constraints.is_file():
        command.extend(["--constraint", str(constraints)])
    command.extend(["-r", str(requirements)])
    if extra_args:
        command.extend(extra_args)
    return command


def _build_poetry_command(
    poetry_invocation: Sequence[str],
    extras: Iterable[str],
    include_dev: bool,
    poetry_args: Sequence[str] | None,
) -> list[str]:
    command: list[str] = list(poetry_invocation)
    command.extend(["install", "--sync"])
    for extra in extras:
        extra_normalised = extra.strip()
        if extra_normalised:
            command.extend(["--extras", extra_normalised])
    if include_dev:
        command.extend(["--with", "dev"])
    if poetry_args:
        command.extend(poetry_args)
    return command


def _install_with_pip(
    python_executable: Path,
    wheelhouse: Path,
    requirements: Path,
    *,
    upgrade: bool,
    extra_args: Sequence[str] | None,
    constraints: Path | None,
    env: Mapping[str, str],
    dry_run: bool,
) -> int:
    command = _build_pip_command(
        python_executable,
        wheelhouse,
        requirements,
        upgrade=upgrade,
        extra_args=extra_args,
        constraints=constraints,
    )
    return _execute_with_reporting(
        command, env=env, dry_run=dry_run, label="pip install"
    )


def _install_with_poetry(
    poetry_invocation: Sequence[str],
    extras: Iterable[str],
    include_dev: bool,
    poetry_args: Sequence[str],
    *,
    env: Mapping[str, str],
    dry_run: bool,
) -> int:
    command = _build_poetry_command(poetry_invocation, extras, include_dev, poetry_args)
    return _execute_with_reporting(
        command, env=env, dry_run=dry_run, label="poetry install"
    )


def _resolve_python_executable(args: argparse.Namespace) -> tuple[Path, Path | None]:
    if args.venv:
        python_path = _ensure_virtualenv(args.venv)
        return python_path, args.venv.resolve()
    python_path = args.python.resolve()
    if not python_path.exists():
        raise FileNotFoundError(f"Python interpreter not found: {python_path}")
    return python_path, None


def _ensure_poetry_invocation(
    preferred_bin: str,
    python_executable: Path,
    *,
    env: MutableMapping[str, str],
    wheelhouse: Path,
    dry_run: bool,
) -> Sequence[str]:
    def _is_available(binary: str) -> bool:
        path_value = env.get("PATH", os.defpath)
        return bool(shutil.which(binary, path=path_value)) or Path(binary).exists()

    if preferred_bin and _is_available(preferred_bin):
        return [preferred_bin]

    if _is_available("poetry"):
        return ["poetry"]

    command = [str(python_executable), "-m", "poetry"]
    if dry_run:
        return command

    try:
        subprocess.run(  # noqa: S603 - command constructed from trusted constants
            command + ["--version"],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        install_cmd = [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "--upgrade",
            "poetry==2.2.1",
            "poetry-plugin-export",
        ]
        subprocess.run(  # noqa: S603 - command uses trusted arguments
            install_cmd, check=True, env=env
        )
    else:
        return command

    if _is_available("poetry"):
        return ["poetry"]

    subprocess.run(  # noqa: S603 - poetry command built from trusted components
        command + ["--version"],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return command


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _maybe_fetch_archives(args)

    wheelhouse = args.wheelhouse.resolve()
    requirements = (args.requirements or (wheelhouse / "requirements.txt")).resolve()
    _validate_inputs(parser, wheelhouse, requirements)

    metadata = _load_wheelhouse_metadata(wheelhouse)
    extras = tuple(args.extras) if args.extras else metadata.extras
    include_dev = metadata.include_dev if args.include_dev is None else args.include_dev
    _report_metadata(metadata, extras, include_dev)

    python_executable, venv_path = _resolve_python_executable(args)
    base_env = _prepare_env(os.environ, wheelhouse, venv_path)

    constraints_path = (args.constraints or DEFAULT_CONSTRAINTS).resolve()
    pip_exit_code = _install_with_pip(
        python_executable,
        wheelhouse,
        requirements,
        upgrade=not args.no_pip_upgrade,
        extra_args=args.pip_extra_args,
        constraints=constraints_path if constraints_path.is_file() else None,
        env=base_env,
        dry_run=args.dry_run,
    )
    if pip_exit_code != 0:
        return pip_exit_code

    _maybe_install_uv(args, wheelhouse, venv_path)

    if args.no_poetry:
        return 0

    poetry_env = _prepare_env(base_env, wheelhouse, venv_path)
    poetry_invocation = _ensure_poetry_invocation(
        args.poetry_bin,
        python_executable,
        env=poetry_env,
        wheelhouse=wheelhouse,
        dry_run=args.dry_run,
    )
    poetry_exit_code = _install_with_poetry(
        poetry_invocation,
        extras,
        include_dev,
        tuple(args.poetry_args or ()),
        env=poetry_env,
        dry_run=args.dry_run,
    )
    return poetry_exit_code


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
