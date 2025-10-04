#!/usr/bin/env python3
"""Analyse dependency drift using SBOM and metadata snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

RISK_SAFE = "up-to-date"
RISK_PATCH = "patch"
RISK_MINOR = "minor"
RISK_MAJOR = "major"
RISK_CONFLICT = "conflict"
RISK_UNKNOWN = "unknown"


@dataclass(slots=True)
class PackageDrift:
    name: str
    current: str | None
    latest: str | None
    severity: str
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DriftPolicy:
    default_update_window_days: int = 14
    minor_update_window_days: int = 30
    major_review_required: bool = True
    allow_transitive_conflicts: bool = False
    weight_recency: int = 3
    weight_security: int = 5
    weight_contract: int = 4
    weight_success: int = 2
    package_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class DependencyDriftReport:
    generated_at: str
    packages: list[PackageDrift]
    severity: str
    notes: list[str]


def load_sbom(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    components = payload.get("components", [])
    if not isinstance(components, list):  # pragma: no cover - defensive
        raise ValueError("Invalid SBOM: components must be a list")
    return components


def load_metadata(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_policy(raw: dict[str, Any] | None) -> DriftPolicy:
    if raw is None:
        return DriftPolicy()
    overrides_raw = raw.get("package_overrides") or []
    overrides: dict[str, dict[str, Any]] = {}
    if isinstance(overrides_raw, list):
        for entry in overrides_raw:
            if isinstance(entry, dict) and "name" in entry:
                overrides[entry["name"].lower()] = entry
    return DriftPolicy(
        default_update_window_days=int(raw.get("default_update_window_days", 14)),
        minor_update_window_days=int(raw.get("minor_update_window_days", 30)),
        major_review_required=bool(raw.get("major_review_required", True)),
        allow_transitive_conflicts=bool(raw.get("allow_transitive_conflicts", False)),
        weight_recency=int(raw.get("autoresolver_weight_recency", 3)),
        weight_security=int(raw.get("autoresolver_weight_security", 5)),
        weight_contract=int(raw.get("autoresolver_weight_contract", 4)),
        weight_success=int(raw.get("autoresolver_weight_success", 2)),
        package_overrides=overrides,
    )


def _has_name(component: dict[str, Any]) -> bool:
    return bool(str(component.get("name") or "").strip())


def _build_package_drift(
    component: dict[str, Any],
    latest_map: dict[str, Any],
    policy: DriftPolicy,
) -> PackageDrift:
    name = str(component.get("name") or "").strip()
    current_version = component.get("version")
    latest_info = latest_map.get(name.lower()) if isinstance(latest_map, dict) else None
    latest_version = None
    if isinstance(latest_info, dict):
        latest_version = latest_info.get("latest") or latest_info.get("stable")
    severity, entry_notes = _classify_drift(
        name, current_version, latest_version, policy
    )
    return PackageDrift(
        name=name,
        current=str(current_version) if current_version else None,
        latest=str(latest_version) if latest_version else None,
        severity=severity,
        notes=entry_notes,
    )


def evaluate_drift(
    sbom_components: Iterable[dict[str, Any]],
    metadata: dict[str, Any],
    policy: DriftPolicy,
) -> DependencyDriftReport:
    latest_map = (metadata.get("packages") if isinstance(metadata, dict) else {}) or {}
    packages = [
        _build_package_drift(component, latest_map, policy)
        for component in sbom_components
        if _has_name(component)
    ]
    highest = _overall_severity(packages)
    generated_at = datetime.now(UTC).isoformat()
    notes: list[str] = []
    if not metadata:
        notes.append("Metadata snapshot missing or empty; severity may be inaccurate.")
    return DependencyDriftReport(
        generated_at=generated_at,
        packages=sorted(packages, key=lambda item: item.name.lower()),
        severity=highest,
        notes=notes,
    )


def _classify_drift(
    name: str,
    current_version: str | None,
    latest_version: str | None,
    policy: DriftPolicy,
) -> tuple[str, list[str]]:
    if not current_version:
        return RISK_UNKNOWN, ["missing current version"]
    if not latest_version:
        return RISK_UNKNOWN, ["missing metadata"]
    try:
        current = Version(current_version)
        latest = Version(latest_version)
    except InvalidVersion:
        return RISK_UNKNOWN, ["invalid version encountered"]
    if latest <= current:
        return RISK_SAFE, []
    override = policy.package_overrides.get(name.lower())
    if _is_major_upgrade(current, latest):
        notes = [f"major upgrade available ({current_version} -> {latest_version})"]
        if override and override.get("stay_on_major") is not None:
            notes.append("major upgrades require override")
        return RISK_MAJOR, notes
    if current.release[:2] != latest.release[:2]:
        return RISK_MINOR, [
            f"minor upgrade available ({current_version} -> {latest_version})"
        ]
    return RISK_PATCH, [
        f"patch upgrade available ({current_version} -> {latest_version})"
    ]


def _is_major_upgrade(current: Version, latest: Version) -> bool:
    if not current.release or not latest.release:
        return False
    return current.release[0] != latest.release[0]


def _overall_severity(packages: Iterable[PackageDrift]) -> str:
    severity_order = [
        RISK_SAFE,
        RISK_PATCH,
        RISK_MINOR,
        RISK_MAJOR,
        RISK_CONFLICT,
        RISK_UNKNOWN,
    ]
    rank = {name: index for index, name in enumerate(severity_order)}
    highest = RISK_SAFE
    for package in packages:
        if rank.get(package.severity, -1) > rank.get(highest, -1):
            highest = package.severity
    return highest


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate dependency drift using an SBOM and metadata snapshot.",
    )
    parser.add_argument(
        "--sbom", type=Path, required=True, help="Path to CycloneDX SBOM JSON."
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Optional path to JSON metadata with latest version information.",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        help="Optional path to dependency policy JSON extracted from contract.",
    )
    return parser.parse_args(argv)


def _load_policy_from_path(path: Path | None) -> DriftPolicy:
    if path is None:
        return DriftPolicy()
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_policy(data)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    components = load_sbom(args.sbom)
    metadata = load_metadata(args.metadata)
    policy_data = _load_policy_from_path(args.policy)
    report = evaluate_drift(components, metadata, policy_data)
    output = {
        "generated_at": report.generated_at,
        "severity": report.severity,
        "packages": [
            {
                "name": pkg.name,
                "current": pkg.current,
                "latest": pkg.latest,
                "severity": pkg.severity,
                "notes": pkg.notes,
            }
            for pkg in report.packages
        ],
        "notes": report.notes,
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
