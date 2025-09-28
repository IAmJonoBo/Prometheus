#!/usr/bin/env python3
"""Bootstrap tool for installing dependencies from the offline wheelhouse."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import venv
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path

from prometheus.packaging.metadata import WheelhouseManifest, load_wheelhouse_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WHEELHOUSE = REPO_ROOT / "vendor" / "wheelhouse"
DEFAULT_REQUIREMENTS = DEFAULT_WHEELHOUSE / "requirements.txt"


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
		"--requirements",
		type=Path,
		help="Path to requirements.txt exported alongside the wheelhouse (default: <wheelhouse>/requirements.txt)",
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
	parser.set_defaults(include_dev=None)

	return parser


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
		raise RuntimeError(f"Failed to parse wheelhouse manifest at {manifest_path}: {exc}") from exc


def _ensure_virtualenv(path: Path) -> Path:
	resolved = path.resolve()
	if not resolved.exists():
		builder = venv.EnvBuilder(with_pip=True)
		builder.create(resolved)
	if sys.platform == "win32":  # pragma: no cover - platform specific
		python_path = resolved / "Scripts" / "python.exe"
	else:
		python_path = resolved / "bin" / "python"
	if not python_path.exists():  # pragma: no cover - defensive guard for unusual layouts
		raise RuntimeError(f"Python executable not found in virtualenv: {python_path}")
	return python_path


def _prepare_env(base_env: Mapping[str, str], wheelhouse: Path, venv_path: Path | None) -> MutableMapping[str, str]:
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


def _run_command(command: Sequence[str], *, env: Mapping[str, str], dry_run: bool) -> None:
	rendered = " ".join(shlex.quote(part) for part in command)
	print(f"→ {rendered}")
	if dry_run:
		return
	subprocess.run(command, check=True, env=env)


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
	command.extend(["-r", str(requirements)])
	if extra_args:
		command.extend(extra_args)
	return command


def _build_poetry_command(
	poetry_bin: str,
	extras: Iterable[str],
	include_dev: bool,
	poetry_args: Sequence[str] | None,
) -> list[str]:
	command: list[str] = [poetry_bin, "install", "--sync"]
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
	env: Mapping[str, str],
	dry_run: bool,
) -> int:
	command = _build_pip_command(
		python_executable,
		wheelhouse,
		requirements,
		upgrade=upgrade,
		extra_args=extra_args,
	)
	return _execute_with_reporting(command, env=env, dry_run=dry_run, label="pip install")


def _install_with_poetry(
	poetry_bin: str,
	extras: Iterable[str],
	include_dev: bool,
	poetry_args: Sequence[str],
	*,
	env: Mapping[str, str],
	dry_run: bool,
) -> int:
	command = _build_poetry_command(poetry_bin, extras, include_dev, poetry_args)
	return _execute_with_reporting(command, env=env, dry_run=dry_run, label="poetry install")


def _resolve_python_executable(args: argparse.Namespace) -> tuple[Path, Path | None]:
	if args.venv:
		python_path = _ensure_virtualenv(args.venv)
		return python_path, args.venv.resolve()
	python_path = args.python.resolve()
	if not python_path.exists():
		raise FileNotFoundError(f"Python interpreter not found: {python_path}")
	return python_path, None


def main(argv: Sequence[str] | None = None) -> int:
	parser = build_parser()
	args = parser.parse_args(argv)

	wheelhouse = args.wheelhouse.resolve()
	if not wheelhouse.is_dir():
		parser.error(f"Wheelhouse directory not found: {wheelhouse}")

	requirements = (args.requirements or (wheelhouse / "requirements.txt")).resolve()
	if not requirements.is_file():
		parser.error(f"Requirements file not found: {requirements}")

	metadata = _load_wheelhouse_metadata(wheelhouse)
	extras = tuple(args.extras) if args.extras else metadata.extras
	include_dev = metadata.include_dev if args.include_dev is None else args.include_dev

	print("Wheelhouse prepared from commit:", metadata.commit or "<unknown>")
	if metadata.generated_at:
		print("Generated at:", metadata.generated_at)
	if extras:
		print("Installing extras:", ", ".join(extras))
	print("Include dev dependencies:", "yes" if include_dev else "no")

	python_executable, venv_path = _resolve_python_executable(args)
	base_env = _prepare_env(os.environ, wheelhouse, venv_path)

	pip_exit_code = _install_with_pip(
		python_executable,
		wheelhouse,
		requirements,
		upgrade=not args.no_pip_upgrade,
		extra_args=args.pip_extra_args,
		env=base_env,
		dry_run=args.dry_run,
	)
	if pip_exit_code != 0:
		return pip_exit_code

	if args.no_poetry:
		return 0

	poetry_env = _prepare_env(base_env, wheelhouse, venv_path)
	poetry_exit_code = _install_with_poetry(
		args.poetry_bin,
		extras,
		include_dev,
		tuple(args.poetry_args or ()),
		env=poetry_env,
		dry_run=args.dry_run,
	)
	return poetry_exit_code


if __name__ == "__main__":  # pragma: no cover - CLI entry point
	sys.exit(main())
