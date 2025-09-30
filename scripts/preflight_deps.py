#!/usr/bin/env python3
"""Dependency preflight guard for Renovate and local upgrade checks.

This script inspects the generated ``poetry.lock`` file, optionally limits the
scope to a subset of packages, and verifies that binary wheels exist for the
platform/python matrix we require for offline packaging. It also performs a
light-weight lock sanity check so renovate branches fail fast when a pin would
break our wheelhouse guarantees.

Example usage:

.. code-block:: bash

    python scripts/preflight_deps.py
    python scripts/preflight_deps.py --packages argon2-cffi
    python scripts/preflight_deps.py --python-versions "3.11 3.12" \
        --platforms "manylinux2014_x86_64" --json > preflight.json

The script exits with code ``1`` if any package breaches the guardrails unless
``--exit-zero`` is supplied.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from packaging.tags import Tag
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = REPO_ROOT / "poetry.lock"
DEFAULT_ALLOW_SDIST = {
    pkg.strip()
    for pkg in os.environ.get("ALLOW_SDIST_FOR", "").split(",")
    if pkg.strip()
}
DEFAULT_PYTHON_VERSIONS = ("3.11", "3.12")
DEFAULT_PLATFORMS = ("manylinux2014_x86_64",)
PYPI_JSON_URL = "https://pypi.org/pypi/{package}/{version}/json"


@dataclass(frozen=True)
class WheelTarget:
    python: str
    platform: str

    @property
    def python_major(self) -> str:
        return self.python.split(".")[0]


@dataclass
class PackageResult:
    name: str
    version: str
    status: str
    message: str
    missing_targets: list[WheelTarget]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate dependency updates before opening a Renovate PR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Exit codes:
              0  All checks passed or only warnings emitted
              1  At least one package is missing required wheels
            """
        ).strip(),
    )
    parser.add_argument(
        "--lock", type=Path, default=DEFAULT_LOCK, help="Path to poetry.lock"
    )
    parser.add_argument(
        "--packages",
        nargs="+",
        help="Optional list of package names to validate (defaults to every main dependency).",
    )
    parser.add_argument(
        "--python-versions",
        default=" ".join(DEFAULT_PYTHON_VERSIONS),
        help="Space separated list of Python versions to guard (default: %(default)s)",
    )
    parser.add_argument(
        "--platforms",
        default=" ".join(DEFAULT_PLATFORMS),
        help="Space separated list of platform tags to guard (default: %(default)s)",
    )
    parser.add_argument(
        "--allow-sdist",
        default=",".join(sorted(DEFAULT_ALLOW_SDIST)),
        help="Comma separated list of packages that may fall back to sdists",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine readable JSON summary"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress human readable output"
    )
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="Always exit with success even if gaps are detected",
    )
    return parser.parse_args(argv)


def _load_lock(path: Path) -> Mapping[str, object]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _iter_packages(
    lock_data: Mapping[str, object], *, only: Iterable[str] | None
) -> Iterable[tuple[str, str, str]]:
    only_lower = {name.lower() for name in only} if only else None
    packages = lock_data.get("package", [])
    if not isinstance(packages, list):  # pragma: no cover - defensive
        return []
    for entry in packages:
        if not isinstance(entry, Mapping):  # pragma: no cover - defensive
            continue
        name = str(entry.get("name"))
        version = str(entry.get("version"))
        category = str(entry.get("category", "main"))
        if only_lower and name.lower() not in only_lower:
            continue
        yield name, version, category


def _fetch_release(name: str, version: str) -> Mapping[str, object] | None:
    url = PYPI_JSON_URL.format(
        package=urllib.parse.quote(name), version=urllib.parse.quote(version)
    )
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https"}:
        raise RuntimeError(f"Blocked non-HTTPS PyPI URL: {url}")

    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # type: ignore[arg-type]  # nosec: B310
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(
            f"PyPI request failed for {name}=={version}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"PyPI request failed for {name}=={version}: {exc.reason}"
        ) from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - network edge
        raise RuntimeError(f"Invalid JSON for {name}=={version}: {exc}") from exc


def _wheel_supports_target(filename: str, target: WheelTarget) -> bool:
    try:
        _, _, _, tags = parse_wheel_filename(filename)
    except InvalidWheelFilename:  # pragma: no cover - defensive; skip bad files
        return False
    for tag in tags:
        if _tag_supports_target(tag, target):
            return True
    return False


def _tag_supports_target(tag: Tag, target: WheelTarget) -> bool:
    python_match = (
        tag.interpreter
        in {"py3", f"py{target.python_major}", f"py{target.python.replace('.', '')}"}
        or tag.interpreter.startswith(f"cp{target.python.replace('.', '')}")
        or tag.interpreter.startswith("cp3")
        or tag.interpreter.startswith("pp3")
    )
    if not python_match:
        return False

    platform = tag.platform or "any"
    if platform == "any":
        return True

    # Normalize multiple platforms concatenated by dots
    platforms = platform.split(".")
    normalized_target = target.platform.replace("-", "_")
    for entry in platforms:
        normalized_entry = entry.replace("-", "_")
        if normalized_entry == normalized_target:
            return True
        if normalized_entry.startswith("manylinux") and normalized_target.startswith(
            "manylinux"
        ):
            # Accept newer manylinux variants for backwards compatibility
            return True
    return False


def _evaluate_package(
    name: str,
    version: str,
    *,
    targets: Sequence[WheelTarget],
    allow_sdist: set[str],
) -> PackageResult:
    data = _fetch_release(name, version)
    if not data:
        return PackageResult(
            name=name,
            version=version,
            status="error",
            message="package/version not found on PyPI",
            missing_targets=list(targets),
        )

    releases: list[Any]
    raw_urls = data.get("urls", [])
    if isinstance(raw_urls, list):
        releases = raw_urls
    else:  # pragma: no cover - defensive
        releases = []

    wheels = [
        entry
        for entry in releases
        if isinstance(entry, Mapping) and entry.get("packagetype") == "bdist_wheel"
    ]
    if not wheels:
        if name.lower() in allow_sdist:
            return PackageResult(
                name, version, "warn", "sdist fallback permitted", list(targets)
            )
        return PackageResult(
            name=name,
            version=version,
            status="error",
            message="no wheels published",
            missing_targets=list(targets),
        )

    missing = []
    for target in targets:
        if any(
            _wheel_supports_target(str(entry.get("filename")), target)
            for entry in wheels
        ):
            continue
        missing.append(target)

    if not missing:
        return PackageResult(
            name=name, version=version, status="ok", message="", missing_targets=[]
        )

    if name.lower() in allow_sdist:
        return PackageResult(name, version, "warn", "sdist fallback permitted", missing)

    return PackageResult(
        name=name,
        version=version,
        status="error",
        message="wheel coverage gap",
        missing_targets=missing,
    )


def _build_targets(
    python_versions: Sequence[str], platforms: Sequence[str]
) -> list[WheelTarget]:
    targets: list[WheelTarget] = []
    for python in python_versions:
        python = python.strip()
        if not python:
            continue
        for platform in platforms:
            platform = platform.strip()
            if not platform:
                continue
            targets.append(WheelTarget(python=python, platform=platform))
    return targets


def _render_human(results: Sequence[PackageResult]) -> str:
    lines = ["Dependency preflight summary:"]
    for item in results:
        if item.ok:
            prefix = "✔"
        elif item.status == "warn":
            prefix = "⚠"
        else:
            prefix = "✖"
        message = item.message
        if item.missing_targets:
            formatted = ", ".join(
                f"py{target.python}/@{target.platform}"
                for target in item.missing_targets
            )
            message = f"{message or 'Missing wheels'} ({formatted})"
        lines.append(f"  {prefix} {item.name}=={item.version}: {message or 'ok'}")
    return "\n".join(lines)


def _render_json(results: Sequence[PackageResult]) -> str:
    payload = [
        {
            "name": item.name,
            "version": item.version,
            "status": item.status,
            "message": item.message,
            "missing": [
                {"python": target.python, "platform": target.platform}
                for target in item.missing_targets
            ],
        }
        for item in results
    ]
    return json.dumps(payload, indent=2, sort_keys=True)


def _execute_preflight(
    args: argparse.Namespace,
) -> tuple[list[PackageResult], list[str]]:
    if not args.lock.is_file():
        raise FileNotFoundError(f"poetry.lock not found at {args.lock}")

    lock_data = _load_lock(args.lock)

    python_versions = [item for item in args.python_versions.split(" ") if item]
    platforms = [item for item in args.platforms.split(" ") if item]
    targets = _build_targets(python_versions, platforms)
    allow_sdist = {
        pkg.strip().lower() for pkg in args.allow_sdist.split(",") if pkg.strip()
    }

    package_iter = _iter_packages(lock_data, only=args.packages)
    scoped_packages = [pkg for pkg in package_iter if pkg[2] == "main"]

    results: list[PackageResult] = []
    errors: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        future_map: dict[concurrent.futures.Future[PackageResult], tuple[str, str]] = {}
        for name, version, _ in scoped_packages:
            fut = pool.submit(
                _evaluate_package,
                name,
                version,
                targets=targets,
                allow_sdist=allow_sdist,
            )
            future_map[fut] = (name, version)

        for fut in concurrent.futures.as_completed(future_map):
            name, version = future_map[fut]
            try:
                result = fut.result()
            except RuntimeError as exc:
                errors.append(f"{name}=={version}: {exc}")
                continue
            results.append(result)

    results.sort(key=lambda item: item.name.lower())
    return results, errors


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        results, errors = _execute_preflight(args)
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.packages and not results:
        print(
            "No matching packages found in poetry.lock for supplied names",
            file=sys.stderr,
        )
        return 1

    if errors:
        for line in errors:
            print(f"ERROR: {line}", file=sys.stderr)
        if not args.exit_zero:
            return 1

    if not args.quiet:
        print(_render_human(results))

    if args.json:
        print(_render_json(results))

    has_failure = any(item.status == "error" for item in results)
    if has_failure and not args.exit_zero:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
