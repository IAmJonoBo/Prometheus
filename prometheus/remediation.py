"""Automated remediation helpers for packaging workflows."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import InvalidVersion, Version

ReleaseFetcher = Callable[[str], Mapping[str, object] | None]

_MISSING_DIST_PATTERN = re.compile(
    r"No matching distribution found for ([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)"
)


@dataclass(slots=True)
class WheelhouseFailure:
    """Represents a missing-wheel failure extracted from pip output."""

    package: str
    requested_version: str
    fallback_version: str | None = None
    reason: str = "missing_binary_wheel"
    recommendations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WheelTarget:
    python: str | None
    platform: str | None

    @property
    def python_major(self) -> str | None:
        if self.python is None:
            return None
        return self.python.split(".")[0]


def parse_missing_wheel_failures(log_text: str) -> list[WheelhouseFailure]:
    """Extract missing wheel errors from pip output."""

    failures: list[WheelhouseFailure] = []
    for match in _MISSING_DIST_PATTERN.finditer(log_text):
        package, version = match.groups()
        failures.append(WheelhouseFailure(package=package, requested_version=version))
    return failures


class WheelhouseRemediator:
    """Derive remediation guidance for wheelhouse build failures."""

    def __init__(
        self,
        *,
        python_version: str | None,
        platform: str | None,
        fetch_package: ReleaseFetcher | None = None,
    ) -> None:
        self._target = WheelTarget(python=python_version, platform=platform)
        self._fetch_package = fetch_package or self._fetch_release_data
        self._release_cache: dict[str, Mapping[str, object]] = {}

    def build_summary(
        self,
        log_text: str,
        *,
        include_recommendations: bool = True,
    ) -> dict[str, object] | None:
        failures = parse_missing_wheel_failures(log_text)
        if not failures:
            return None

        for failure in failures:
            fallback = self._suggest_fallback(
                failure.package, failure.requested_version
            )
            failure.fallback_version = fallback
            if include_recommendations:
                failure.recommendations = self._recommendations_for(failure)

        summary = {
            "generated_at": datetime.now(UTC).isoformat(),
            "python_version": self._target.python,
            "platform": self._target.platform,
            "failures": [
                {
                    "package": failure.package,
                    "requested_version": failure.requested_version,
                    "fallback_version": failure.fallback_version,
                    "reason": failure.reason,
                    "recommendations": failure.recommendations,
                }
                for failure in failures
            ],
        }
        return summary

    def write_summary(
        self,
        log_path: Path,
        output_path: Path,
    ) -> dict[str, object] | None:
        log_text = log_path.read_text(encoding="utf-8")
        summary = self.build_summary(log_text)
        if summary is None:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return summary

    def _fetch_release_data(self, package: str) -> Mapping[str, object] | None:
        if package in self._release_cache:
            return self._release_cache[package]
        url = f"https://pypi.org/pypi/{package}/json"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # type: ignore[arg-type]  # nosec: B310
                payload = response.read()
        except urllib.error.HTTPError as exc:  # pragma: no cover - network edge
            if exc.code == 404:
                data = None
            else:
                raise
        except urllib.error.URLError:  # pragma: no cover - network edge
            data = None
        else:
            try:
                data = json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:  # pragma: no cover - malformed payload
                data = None
        if data is not None:
            self._release_cache[package] = data
        return data

    def _suggest_fallback(self, package: str, requested: str) -> str | None:
        try:
            requested_version = Version(requested)
        except InvalidVersion:
            return None

        data = self._fetch_package(package)
        if not data:
            return None

        releases = data.get("releases")
        if not isinstance(releases, Mapping):
            return None

        candidates: list[tuple[Version, Sequence[Mapping[str, object]]]] = []
        for version_str, files in releases.items():
            if not isinstance(files, Sequence):
                continue
            try:
                version = Version(version_str)
            except InvalidVersion:
                continue
            if version >= requested_version:
                # Ignore requested version (already tried) and future versions
                continue
            candidates.append((version, files))

        candidates.sort(reverse=True)
        for version, files in candidates:
            if self._version_has_compatible_wheel(files):
                return str(version)
        return None

    def _version_has_compatible_wheel(
        self, files: Sequence[Mapping[str, object]]
    ) -> bool:
        for file_info in files:
            if not isinstance(file_info, Mapping):
                continue
            if str(file_info.get("packagetype")) != "bdist_wheel":
                continue
            if file_info.get("yanked"):
                continue
            filename = file_info.get("filename")
            if not filename:
                continue
            if not self._wheel_supports(str(filename)):
                continue
            requires_python = file_info.get("requires_python")
            if not self._python_supported(
                str(requires_python) if requires_python else None
            ):
                continue
            return True
        return False

    def _wheel_supports(self, filename: str) -> bool:
        try:
            _, _, _, tags = parse_wheel_filename(filename)
        except InvalidWheelFilename:
            return False
        target = self._target
        for tag in tags:
            if self._tag_supports(tag, target):
                return True
        return False

    def _tag_supports(self, tag, target: WheelTarget) -> bool:
        return self._interpreter_matches(tag, target) and self._platform_matches(
            tag, target
        )

    def _interpreter_matches(self, tag, target: WheelTarget) -> bool:
        python = target.python
        if python is None:
            return True
        py_major = target.python_major
        allowed = {
            f"py{python.replace('.', '')}",
            f"py{py_major}" if py_major else None,
            "py3",
            f"cp{python.replace('.', '')}",
            f"cp{py_major}" if py_major else None,
        }
        allowed = {entry for entry in allowed if entry}
        if tag.interpreter in allowed:
            return True
        return tag.interpreter.startswith("cp3")

    def _platform_matches(self, tag, target: WheelTarget) -> bool:
        platform = target.platform
        if platform is None:
            return True
        if tag.platform in {"any", None}:
            return True
        normalized_target = platform.replace("-", "_")
        for entry in str(tag.platform).split("."):
            normalized_entry = entry.replace("-", "_")
            if normalized_entry == normalized_target:
                return True
            if normalized_entry.startswith(
                "manylinux"
            ) and normalized_target.startswith("manylinux"):
                return True
        return False

    def _python_supported(self, requires_python: str | None) -> bool:
        if not requires_python or self._target.python is None:
            return True
        try:
            spec = SpecifierSet(requires_python)
        except InvalidSpecifier:
            return True
        try:
            py_version = Version(self._target.python)
        except InvalidVersion:
            return True
        return py_version in spec

    def _recommendations_for(self, failure: WheelhouseFailure) -> list[str]:
        recs: list[str] = []
        python_version = self._target.python or "the targeted Python runtime"
        platform = self._target.platform or "target platforms"
        if failure.fallback_version:
            recs.append(
                f"Pin {failure.package}=={failure.fallback_version} until binary wheels "
                f"are published for {python_version} on {platform}."
            )
        else:
            recs.append(
                f"Hold the {failure.package} upgrade or request wheels for {python_version} "
                f"on {platform}."
            )
        recs.append(
            f"As a temporary escape hatch, add {failure.package} to ALLOW_SDIST_FOR "
            "when invoking scripts/build-wheelhouse.sh (compilation toolchain required)."
        )
        return recs


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated remediation helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    wheelhouse = subparsers.add_parser(
        "wheelhouse", help="Summarise pip wheel download failures"
    )
    wheelhouse.add_argument("--log", type=Path, required=True)
    wheelhouse.add_argument("--output", type=Path, required=True)
    wheelhouse.add_argument("--python-version", dest="python_version", default=None)
    wheelhouse.add_argument("--platform", dest="platform", default=None)
    wheelhouse.add_argument(
        "--no-recommendations",
        dest="include_recommendations",
        action="store_false",
        help="Skip generating human recommendations",
    )
    wheelhouse.set_defaults(include_recommendations=True)

    return parser.parse_args(argv)


def _handle_wheelhouse(args: argparse.Namespace) -> int:
    if not args.log.exists():
        print(f"Log file not found: {args.log}", file=sys.stderr)
        return 1
    remediator = WheelhouseRemediator(
        python_version=args.python_version,
        platform=args.platform,
    )
    summary = remediator.write_summary(args.log, args.output)
    if summary is None:
        print("No missing wheel failures detected", file=sys.stderr)
        return 0
    failures = summary.get("failures", [])
    if not isinstance(failures, list):
        failures = []
    print("Wheelhouse remediation summary:")
    for failure in failures:
        pkg = failure.get("package")
        requested = failure.get("requested_version")
        fallback = failure.get("fallback_version")
        print(f"  - {pkg}=={requested}")
        if fallback:
            print(f"    fallback: {fallback}")
        for rec in failure.get("recommendations", []):
            print(f"    • {rec}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "wheelhouse":
        return _handle_wheelhouse(args)
    print(f"Unsupported command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
