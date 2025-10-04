#!/usr/bin/env python3
"""Synchronise dependency manifests from the contract file."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = DEFAULT_REPO_ROOT / "configs" / "dependency-profile.toml"
DEFAULT_ROOT_CONSTRAINTS = DEFAULT_REPO_ROOT / "constraints" / "runtime-roots.txt"
DEFAULT_ROOT_DIST = DEFAULT_REPO_ROOT / "dist" / "requirements.txt"
DEFAULT_ROOT_WHEELHOUSE = (
    DEFAULT_REPO_ROOT / "vendor" / "wheelhouse" / "runtime-roots.txt"
)

ALLOWED_DRIFT_STATUSES = {"drift", "exception"}
GENERATED_HEADER = "# Generated from dependency-profile.toml"
PYPROJECT_HEADER_NOTE = "# Copy relevant sections into pyproject.toml"


class ContractError(RuntimeError):
    """Raised when the dependency contract cannot be parsed."""


class ManifestWriteError(RuntimeError):
    """Raised when output manifests cannot be written safely."""


@dataclass
class PackageRecord:
    """Structured package entry loaded from the dependency contract."""

    name: str
    profile: str
    constraint: str | None = None
    locked: str | None = None
    extras: tuple[str, ...] = ()
    marker: str | None = None
    owner: str | None = None
    status: str | None = None
    notes: str | None = None

    def requirement(self, prefer_locked: bool = True) -> str:
        """Render the package as a requirement string."""

        spec = self.requirement_without_marker(prefer_locked=prefer_locked)
        if self.marker:
            return f"{spec}; {self.marker}"
        return spec

    def requirement_without_marker(self, prefer_locked: bool = True) -> str:
        """Render requirement without appending an environment marker."""

        base = self._format_name()
        if prefer_locked and self.locked:
            return f"{base}=={self.locked}"
        if self.constraint:
            return f"{base}{self.constraint}"
        if self.locked:
            return f"{base}=={self.locked}"
        message = f"Package {self.name!r} is missing constraint and locked version."
        raise ContractError(message)

    def constraint_satisfied(self) -> bool:
        """Whether the locked version satisfies the declared constraint."""

        if not (self.constraint and self.locked):
            return True
        spec = SpecifierSet(self.constraint)
        return Version(self.locked) in spec

    def _format_name(self) -> str:
        if self.extras:
            extras = ",".join(sorted(self.extras))
            return f"{self.name}[{extras}]"
        return self.name


@dataclass
class Profile:
    """Profile grouping from the contract (runtime, optional extras, etc)."""

    name: str
    raw: Mapping[str, object]
    packages: list[PackageRecord] = field(default_factory=list)

    @property
    def condition(self) -> str | None:
        value = self.raw.get("condition") if isinstance(self.raw, Mapping) else None
        return str(value) if value is not None else None


@dataclass
class PyprojectBlock:
    dependencies: list[str]
    optional: dict[str, list[str]]
    dev_group: dict[str, str]


@dataclass
class ManifestBundle:
    pyproject: PyprojectBlock
    constraints_lines: list[str]
    dist_lines: list[str]
    wheelhouse_lines: list[str]
    root_constraints_lines: list[str]
    root_dist_lines: list[str]
    root_wheelhouse_lines: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class OutputTargets:
    pyproject: Path
    constraints: Path
    dist: Path
    wheelhouse: Path
    root_constraints: Path
    root_dist: Path
    root_wheelhouse: Path
    sbom: Path


class DependencyContract:
    """Helper to load and query the dependency contract."""

    def __init__(self, data: Mapping[str, object], source: Path):
        self._data = data
        self._source = source
        self._profiles = self._parse_profiles()
        self.packages = tuple(
            package
            for profile in self._profiles.values()
            for package in profile.packages
        )

    @property
    def source(self) -> Path:
        return self._source

    def get_profile(self, name: str) -> Profile | None:
        return self._profiles.get(name)

    def iter_profiles(self) -> Iterable[Profile]:
        return self._profiles.values()

    def collect_warnings(self) -> list[str]:
        warnings: list[str] = []
        for package in self.packages:
            if package.constraint and not package.locked:
                warnings.append(
                    f"{package.name} in profile {package.profile} lacks a locked version"
                )
            if not package.constraint and not package.locked:
                warnings.append(
                    f"{package.name} in profile {package.profile} has no constraint or lock"
                )
            if (
                package.constraint
                and package.locked
                and not package.constraint_satisfied()
            ):
                if package.status in ALLOWED_DRIFT_STATUSES:
                    warnings.append(
                        f"Constraint mismatch for {package.name} ({package.profile}) "
                        f"acknowledged via status={package.status}"
                    )
                else:
                    warnings.append(
                        f"Constraint mismatch for {package.name} "
                        f"({package.profile}): {package.locked} !~= {package.constraint}"
                    )
        return warnings

    def to_manifests(self) -> ManifestBundle:
        pyproject = self._build_pyproject_block()
        constraints_lines = self._build_constraints_lines()
        dist_lines = self._build_dist_lines()
        wheelhouse_lines = self._build_wheelhouse_lines()
        root_constraints = [
            GENERATED_HEADER,
            "# Contract-managed root constraint pins.",
        ]
        root_constraints.extend(constraints_lines[2:])
        root_dist = [GENERATED_HEADER, "# Contract-managed root dist pins."]
        root_dist.extend(dist_lines[2:])
        root_wheelhouse = [GENERATED_HEADER, "# Contract-managed root wheelhouse pins."]
        root_wheelhouse.extend(wheelhouse_lines[2:])
        warnings = self.collect_warnings()
        return ManifestBundle(
            pyproject=pyproject,
            constraints_lines=constraints_lines,
            dist_lines=dist_lines,
            wheelhouse_lines=wheelhouse_lines,
            root_constraints_lines=root_constraints,
            root_dist_lines=root_dist,
            root_wheelhouse_lines=root_wheelhouse,
            warnings=warnings,
        )

    def _parse_profiles(self) -> dict[str, Profile]:
        profiles_raw = self._data.get("profiles")
        if not isinstance(profiles_raw, Mapping):
            raise ContractError("Contract is missing a 'profiles' mapping section.")

        profiles: dict[str, Profile] = {}
        for name, payload in profiles_raw.items():
            if not isinstance(payload, Mapping):
                logging.debug(
                    "Skipping profile %s because payload is not a mapping", name
                )
                continue
            profile = self._build_profile(name, payload)
            profiles[name] = profile
        return profiles

    def _build_profile(self, name: str, payload: Mapping[str, object]) -> Profile:
        profile = Profile(name=name, raw=dict(payload))
        packages_data = payload.get("packages") or []
        if not packages_data:
            return profile
        if not isinstance(packages_data, Sequence):
            raise ContractError(f"Profile {name!r} packages must be a sequence.")
        for entry in packages_data:
            package = self._parse_package_entry(name, entry)
            profile.packages.append(package)
        return profile

    def _parse_package_entry(self, profile_name: str, entry: object) -> PackageRecord:
        if not isinstance(entry, Mapping):
            raise ContractError(
                f"Profile {profile_name!r} contains a non-mapping package entry: {entry!r}"
            )
        if "name" not in entry:
            raise ContractError(
                f"Profile {profile_name!r} package entry is missing the 'name' field: {entry!r}"
            )
        extras_value = entry.get("extras") or []
        if extras_value and not isinstance(extras_value, Sequence):
            raise ContractError(
                f"Profile {profile_name!r} extras must be a sequence: {entry!r}"
            )
        extras = tuple(str(extra) for extra in extras_value)
        return PackageRecord(
            name=str(entry["name"]),
            profile=profile_name,
            constraint=_coerce_optional_str(entry.get("constraint")),
            locked=_coerce_optional_str(entry.get("locked")),
            extras=extras,
            marker=_coerce_optional_str(entry.get("marker")),
            owner=_coerce_optional_str(entry.get("owner")),
            status=_coerce_optional_str(entry.get("status")),
            notes=_coerce_optional_str(entry.get("notes")),
        )

    def _build_pyproject_block(self) -> PyprojectBlock:
        runtime_profile = self.get_profile("runtime")
        if not runtime_profile or not runtime_profile.packages:
            raise ContractError(
                "Contract must define profile 'runtime' with at least one package."
            )

        runtime_reqs = sorted(
            {pkg.requirement() for pkg in runtime_profile.packages},
            key=str.casefold,
        )

        optional: dict[str, list[str]] = {}
        for profile in self.iter_profiles():
            condition = profile.condition or ""
            if not condition.startswith("extra:"):
                continue
            extra_name = condition.split(":", 1)[1]
            requirements = sorted(
                {pkg.requirement(prefer_locked=False) for pkg in profile.packages},
                key=str.casefold,
            )
            optional[extra_name] = requirements

        dev_profile = self.get_profile("dev_tooling")
        dev_group: dict[str, str] = {}
        if dev_profile:
            for pkg in dev_profile.packages:
                dev_group[pkg.name] = pkg.requirement()

        return PyprojectBlock(
            dependencies=runtime_reqs,
            optional=optional,
            dev_group=dict(
                sorted(dev_group.items(), key=lambda item: item[0].casefold())
            ),
        )

    def _build_constraints_lines(self) -> list[str]:
        packages = _dedupe_by_name(self.packages)
        lines: list[str] = [GENERATED_HEADER, "# Do not edit by hand."]
        for package in sorted(
            packages,
            key=lambda item: (item.name.casefold(), (item.marker or "").casefold()),
        ):
            if not package.locked:
                continue
            line = package.requirement()
            suffix = _format_status_comment(package)
            if suffix:
                line = f"{line}  {suffix}"
            lines.append(line)
        return lines

    def _build_dist_lines(self) -> list[str]:
        packages = _dedupe_by_name(self.packages)
        lines: list[str] = [
            GENERATED_HEADER,
            "# Pinned requirements for dist artifacts.",
        ]
        for package in sorted(
            packages,
            key=lambda item: (item.name.casefold(), (item.marker or "").casefold()),
        ):
            requirement = package.requirement()
            suffix = _format_status_comment(package)
            if suffix:
                requirement = f"{requirement}  {suffix}"
            lines.append(requirement)
        return lines

    def _build_wheelhouse_lines(self) -> list[str]:
        packages = _dedupe_by_name(self.packages)
        lines: list[str] = [
            GENERATED_HEADER,
            "# Wheelhouse manifest pinned to locked versions.",
        ]
        for package in sorted(
            packages,
            key=lambda item: (item.name.casefold(), (item.marker or "").casefold()),
        ):
            if not package.locked:
                continue
            line = package.requirement()
            suffix = _format_status_comment(package)
            if suffix:
                line = f"{line}  {suffix}"
            lines.append(line)
        return lines


def _dedupe_by_name(packages: Iterable[PackageRecord]) -> list[PackageRecord]:
    by_key: dict[tuple[str, str | None], PackageRecord] = {}
    for package in packages:
        key = (package.name, package.marker)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = package
            continue
        if existing.locked and package.locked and existing.locked != package.locked:
            raise ContractError(
                f"Conflicting locked versions for {package.name}"
                f" (marker={package.marker or 'none'}):"
                f" {existing.locked} vs {package.locked}"
            )
        if not existing.locked and package.locked:
            by_key[key] = package
    return list(by_key.values())


def _coerce_optional_str(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _format_status_comment(package: PackageRecord) -> str:
    parts: list[str] = []
    if package.status:
        parts.append(f"# status: {package.status}")
    if package.notes:
        parts.append(f"# notes: {package.notes}")
    return " ".join(parts)


def _render_pyproject(block: PyprojectBlock) -> str:
    lines: list[str] = [
        GENERATED_HEADER,
        PYPROJECT_HEADER_NOTE,
        "[project]",
        "dependencies = [",
    ]
    for dependency in block.dependencies:
        lines.append(f'  "{dependency}",')
    lines.append("]")

    if block.optional:
        lines.append("")
        lines.append("[project.optional-dependencies]")
        for extra, requirements in sorted(block.optional.items()):
            lines.append(f"{extra} = [")
            for requirement in requirements:
                lines.append(f'  "{requirement}",')
            lines.append("]")

    if block.dev_group:
        lines.append("")
        lines.append("[tool.poetry.group.dev.dependencies]")
        for name, spec in block.dev_group.items():
            lines.append(f'{name} = "{spec}"')

    lines.append("")
    return "\n".join(lines)


def _render_cyclonedx_sbom(contract: DependencyContract) -> str:
    deduped = _dedupe_by_name(contract.packages)
    generated = datetime.now(UTC).isoformat()
    components = [
        _package_to_component(package)
        for package in sorted(deduped, key=lambda item: item.name.casefold())
    ]
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": generated,
            "tools": [
                {
                    "vendor": "prometheus",
                    "name": "sync-dependencies",
                    "version": "1.0.0",
                }
            ],
            "component": {
                "type": "application",
                "name": "prometheus",
                "version": "contract-managed",
                "properties": [
                    {
                        "name": "contract_path",
                        "value": str(contract.source),
                    }
                ],
            },
        },
        "components": components,
    }
    return json.dumps(sbom, indent=2, sort_keys=False) + "\n"


def _package_to_component(package: PackageRecord) -> dict[str, object]:
    version = package.locked or "unknown"
    component: dict[str, object] = {
        "type": "library",
        "name": package.name,
        "version": version,
        "scope": "required",
    }
    purl_version = version if version != "unknown" else None
    if purl_version:
        component["purl"] = f"pkg:pypi/{package.name}@{purl_version}"
    properties = _package_properties(package)
    if properties:
        component["properties"] = properties
    return component


def _package_properties(package: PackageRecord) -> list[dict[str, str]]:
    properties: list[dict[str, str]] = []
    if package.constraint:
        properties.append({"name": "constraint", "value": package.constraint})
    if package.marker:
        properties.append({"name": "marker", "value": package.marker})
    if package.status:
        properties.append({"name": "status", "value": package.status})
    if package.notes:
        properties.append({"name": "notes", "value": package.notes})
    return properties


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate dependency manifests from configs/dependency-profile.toml. "
            "By default the script previews the derived files; pass --apply to "
            "write them to disk."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Repository root containing configs/ and manifests.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
        help="Path to the dependency contract TOML file.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write outputs to disk instead of printing the preview.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files when running with --apply.",
    )
    parser.add_argument(
        "--pyproject-output",
        type=Path,
        help="Override the output path for the generated pyproject snippet.",
    )
    parser.add_argument(
        "--constraints-output",
        type=Path,
        help="Override the output path for the generated constraints file.",
    )
    parser.add_argument(
        "--root-constraints-output",
        type=Path,
        help="Override the output path for the generated root constraints file.",
    )
    parser.add_argument(
        "--dist-output",
        type=Path,
        help="Override the output path for the generated dist requirements file.",
    )
    parser.add_argument(
        "--root-dist-output",
        type=Path,
        help="Override the output path for the generated root dist requirements file.",
    )
    parser.add_argument(
        "--wheelhouse-output",
        type=Path,
        help="Override the output path for the generated wheelhouse manifest.",
    )
    parser.add_argument(
        "--root-wheelhouse-output",
        type=Path,
        help="Override the output path for the generated root wheelhouse manifest.",
    )
    parser.add_argument(
        "--sbom-output",
        type=Path,
        help="Optional path for a CycloneDX SBOM describing resolved packages.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting.",
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def _load_contract(path: Path) -> Mapping[str, object]:
    with path.open("rb") as handler:
        return tomllib.load(handler)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _resolve_contract_path(candidate: Path, repo_root: Path) -> Path:
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _determine_output_targets(
    args: argparse.Namespace, repo_root: Path
) -> OutputTargets:
    generated_dir = repo_root / "var" / "dependency-sync"
    defaults = OutputTargets(
        pyproject=generated_dir / "pyproject.dependencies.generated.toml",
        constraints=generated_dir / "constraints.generated.txt",
        dist=generated_dir / "dist.requirements.generated.txt",
        wheelhouse=generated_dir / "wheelhouse.requirements.generated.txt",
        root_constraints=DEFAULT_ROOT_CONSTRAINTS,
        root_dist=DEFAULT_ROOT_DIST,
        root_wheelhouse=DEFAULT_ROOT_WHEELHOUSE,
        sbom=(repo_root / "var" / "upgrade-guard" / "sbom" / "latest.json"),
    )
    return OutputTargets(
        pyproject=_resolve_output_path(
            args.pyproject_output, repo_root, defaults.pyproject
        ),
        constraints=_resolve_output_path(
            args.constraints_output, repo_root, defaults.constraints
        ),
        dist=_resolve_output_path(args.dist_output, repo_root, defaults.dist),
        wheelhouse=_resolve_output_path(
            args.wheelhouse_output, repo_root, defaults.wheelhouse
        ),
        root_constraints=_resolve_output_path(
            getattr(args, "root_constraints_output", None),
            repo_root,
            defaults.root_constraints,
        ),
        root_dist=_resolve_output_path(
            getattr(args, "root_dist_output", None), repo_root, defaults.root_dist
        ),
        root_wheelhouse=_resolve_output_path(
            getattr(args, "root_wheelhouse_output", None),
            repo_root,
            defaults.root_wheelhouse,
        ),
        sbom=_resolve_output_path(
            getattr(args, "sbom_output", None), repo_root, defaults.sbom
        ),
    )


def _resolve_output_path(
    candidate: Path | None, repo_root: Path, default: Path
) -> Path:
    if candidate is None:
        return default.resolve()
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _write_outputs(
    targets: OutputTargets,
    manifests: ManifestBundle,
    contract: DependencyContract,
    *,
    force: bool,
) -> None:
    for path, payload in (
        (targets.pyproject, _render_pyproject(manifests.pyproject)),
        (targets.constraints, "\n".join(manifests.constraints_lines) + "\n"),
        (targets.dist, "\n".join(manifests.dist_lines) + "\n"),
        (targets.wheelhouse, "\n".join(manifests.wheelhouse_lines) + "\n"),
        (targets.root_constraints, "\n".join(manifests.root_constraints_lines) + "\n"),
        (targets.root_dist, "\n".join(manifests.root_dist_lines) + "\n"),
        (targets.root_wheelhouse, "\n".join(manifests.root_wheelhouse_lines) + "\n"),
    ):
        if path.exists() and not force:
            raise ManifestWriteError(
                f"Refusing to overwrite existing file {path}. Pass --force to override."
            )
        _ensure_parent(path)
        path.write_text(payload)
        logging.info("Wrote %s", path)

    sbom_payload = _render_cyclonedx_sbom(contract)
    if targets.sbom.exists() and not force:
        raise ManifestWriteError(
            f"Refusing to overwrite existing file {targets.sbom}. Pass --force to override."
        )
    _ensure_parent(targets.sbom)
    targets.sbom.write_text(sbom_payload)
    logging.info("Wrote %s", targets.sbom)


def _preview_manifests(manifests: ManifestBundle) -> None:
    print(_render_pyproject(manifests.pyproject))
    print("\n".join(manifests.constraints_lines))
    print()
    print("\n".join(manifests.dist_lines))
    print()
    print("\n".join(manifests.wheelhouse_lines))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    repo_root = args.repo_root.resolve()
    contract_path = _resolve_contract_path(args.contract, repo_root)
    if not contract_path.exists():
        parser.error(f"Contract file not found: {contract_path}")

    logging.debug("Loading contract from %s", contract_path)
    contract_data = _load_contract(contract_path)
    contract = DependencyContract(contract_data, contract_path)
    manifests = contract.to_manifests()

    if args.apply:
        targets = _determine_output_targets(args, repo_root)
        try:
            _write_outputs(targets, manifests, contract, force=args.force)
        except ManifestWriteError as exc:  # pragma: no cover - CLI guard
            parser.error(str(exc))
    else:
        _preview_manifests(manifests)

    if manifests.warnings:
        logging.warning("Contract warnings detected:")
        for warning in manifests.warnings:
            logging.warning("- %s", warning)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
